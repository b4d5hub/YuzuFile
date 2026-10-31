from __future__ import annotations

import json
import os
import sqlite3
import stat
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from platformdirs import user_data_path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_home() -> Path:
    return user_data_path("YuzuFile", appauthor=False)


def owned_path(root: Path, relative: str) -> Path:
    """Reject traversal and links/junctions, including links to paths inside root."""
    relative_path = Path(relative)
    if relative_path.is_absolute() or not relative_path.parts or ".." in relative_path.parts:
        raise ValueError("Unsafe artifact path")
    root = root.absolute()
    candidate = root / relative_path
    for part in (root, *root.parents):
        if is_link(part):
            raise ValueError("Library paths must not contain links or junctions")
    current = root
    for component in relative_path.parts:
        current /= component
        if is_link(current):
            raise ValueError("Artifact paths must not contain links or junctions")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("Artifact is outside its job directory")
    return candidate


def is_link(path: Path) -> bool:
    return path.is_symlink() or (os.name == "nt" and path.exists()
        and bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT))


def clean_staging(root: Path):
    staging = owned_path(root, "staging")
    if staging.exists():
        # Validate all descendants before recursive cleanup, including junctions.
        for directory, dirs, files in os.walk(staging, followlinks=False):
            for name in dirs + files:
                owned_path(root, str((Path(directory) / name).relative_to(root)))
        shutil.rmtree(staging)


class Store:
    def __init__(self, home: Path | None = None):
        self.home = (home or default_home()).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.lock = (self.home / "instance.lock").open("a+b")
        if (self.home / "instance.lock").stat().st_size == 0:
            self.lock.write(b"0")
            self.lock.flush()
        self.lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise ValueError("yuzufile is already using this library. Close the other app or CLI conversion first.") from None
        self.library = self.home / "library"
        self.library.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.home / "history.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
            INSERT OR IGNORE INTO schema_migrations VALUES(1);
            CREATE TABLE IF NOT EXISTS jobs(
                id TEXT PRIMARY KEY, source TEXT NOT NULL, mode TEXT NOT NULL,
                languages TEXT NOT NULL, state TEXT NOT NULL, stage TEXT NOT NULL,
                created TEXT NOT NULL, updated TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS artifacts(
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                path TEXT NOT NULL, kind TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(job_id, path)
            );
        """)
        if "compression" not in {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}:
            self.db.execute("ALTER TABLE jobs ADD COLUMN compression TEXT NOT NULL DEFAULT 'balanced'")
        self.db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(2)")
        if "performance" not in {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}:
            self.db.execute("ALTER TABLE jobs ADD COLUMN performance TEXT NOT NULL DEFAULT 'balanced'")
        self.db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(3)")
        if "output_directory" not in {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}:
            self.db.execute("ALTER TABLE jobs ADD COLUMN output_directory TEXT NOT NULL DEFAULT ''")
        self.db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(4)")
        if "split_settings" not in {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}:
            self.db.execute("ALTER TABLE jobs ADD COLUMN split_settings TEXT NOT NULL DEFAULT '{}'")
        self.db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(5)")
        if "page_plan" not in {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}:
            self.db.execute("ALTER TABLE jobs ADD COLUMN page_plan TEXT NOT NULL DEFAULT '{}'")
        self.db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(6)")
        if 'cleanup_settings' not in {row[1] for row in self.db.execute('PRAGMA table_info(jobs)')}:
            self.db.execute("ALTER TABLE jobs ADD COLUMN cleanup_settings TEXT NOT NULL DEFAULT '{}'")
        self.db.execute('INSERT OR IGNORE INTO schema_migrations VALUES(7)')
        if 'save_beside_source' not in {row[1] for row in self.db.execute('PRAGMA table_info(jobs)')}:
            self.db.execute('ALTER TABLE jobs ADD COLUMN save_beside_source INTEGER NOT NULL DEFAULT 0')
        self.db.execute('INSERT OR IGNORE INTO schema_migrations VALUES(8)')
        self.db.commit()
        self._published_paths={}

    def close(self):
        self.db.close()
        self.lock.close()

    def create(self, source: Path, mode: str, languages: list[str], compression: str = "balanced",
               performance: str = "balanced", output_directory: Path | None = None, split_settings=None, page_plan=None,
               cleanup_settings=None) -> str:
        from yuzufile.performance import performance_profile
        performance_profile(performance)
        from yuzufile.operations import MODES
        if mode not in MODES:
            raise ValueError("Unknown conversion format")
        arrangement = {}
        if mode == 'organize':
            from yuzufile.organize import validate_plan, source_unchanged
            arrangement = validate_plan(page_plan)
            for item in arrangement['sources']:
                source_unchanged(item)
            source = Path(arrangement['sources'][0]['path'])
        from yuzufile.spreads import settings
        split_config = settings(split_settings) if 'split' in MODES[mode] else {}
        from yuzufile.cleanup import settings as cleaning_settings
        cleanup_config = cleaning_settings(cleanup_settings) if 'cleanup' in MODES[mode] else {}
        from yuzufile.compression import LEVELS
        if compression not in LEVELS:
            raise ValueError("Unknown compression level")
        source = source.resolve(strict=True)
        if not source.is_file() or source.suffix.lower() != ".pdf":
            raise ValueError("Select a PDF file")
        job_id = str(uuid4())
        destination = ""
        folder = Path(output_directory).absolute() if output_directory is not None else source.parent
        if not folder.is_dir():
            raise ValueError("The output folder is no longer available. Choose another folder.")
        probe = owned_path(folder, f".yuzufile-write-check-{job_id}")
        try:
            with probe.open("xb"):pass
        except OSError:
            raise ValueError("Cannot write to the output folder. Choose another folder.") from None
        else:probe.unlink()
        destination = str(folder) if output_directory is not None else ''
        with self.db:
            self.db.execute("INSERT INTO jobs(id,source,mode,languages,state,stage,created,updated,compression,performance,output_directory,split_settings,page_plan,cleanup_settings) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (job_id, str(source), mode, json.dumps(languages), "queued", "Queued", now(), now(), compression, performance, destination, json.dumps(split_config), json.dumps(arrangement), json.dumps(cleanup_config)))
            self.db.execute('UPDATE jobs SET save_beside_source=? WHERE id=?',(int(output_directory is None),job_id))
        return job_id

    def job_dir(self, job_id: str) -> Path:
        if str(UUID(job_id)) != job_id:
            raise ValueError("Invalid job ID")
        job = self.get(job_id)
        if job["output_directory"]:
            name = Path(job["source"]).stem[:48].rstrip(" .")
            return owned_path(Path(job["output_directory"]), f"yuzufile-{name}-{job_id}")
        return owned_path(self.library, job_id)

    def get(self, job_id: str) -> dict:
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def jobs(self) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT * FROM jobs ORDER BY created DESC, rowid DESC")]

    def update(self, job_id: str, state: str, stage: str, error: str = ""):
        with self.db:
            self.db.execute("UPDATE jobs SET state=?,stage=?,error=?,updated=? WHERE id=?",
                            (state, stage, error, now(), job_id))

    def artifacts(self, job_id: str) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT * FROM artifacts WHERE job_id=?", (job_id,))]

    def artifact_path(self, job_id, artifact):
        job=self.get(job_id)
        if job['save_beside_source']:
            receipt=owned_path(self.job_dir(job_id),'publication.json')
            if receipt.is_file():
                if job_id not in self._published_paths:
                    if len(self._published_paths)>=64:self._published_paths.pop(next(iter(self._published_paths)))
                    self._published_paths[job_id]=json.loads(receipt.read_text(encoding='utf-8'))
                mapping=self._published_paths[job_id]
                if artifact['path'] in mapping:
                    return owned_path(Path(job['source']).parent,mapping[artifact['path']])
        return owned_path(self.job_dir(job_id),artifact['path'])

    def result_directory(self, job_id):
        job=self.get(job_id)
        if job['save_beside_source']:return Path(job['source']).parent
        return owned_path(self.job_dir(job_id),'result')

    def complete(self, job_id: str):
        root = self.job_dir(job_id)
        manifest = json.loads(owned_path(root, "result/manifest.json").read_text(encoding="utf-8"))
        for artifact in manifest["artifacts"]:
            if not owned_path(root, artifact["path"]).is_file():
                raise ValueError("A conversion output is missing")
        if self.get(job_id)['save_beside_source']:
            from yuzufile.publication import publish_beside_source
            publish_beside_source(root,self.get(job_id)['source'],job_id,manifest['artifacts'])
        with self.db:
            for artifact in manifest["artifacts"]:
                self.db.execute("INSERT OR IGNORE INTO artifacts(job_id,path,kind) VALUES(?,?,?)",
                                (job_id, artifact["path"], artifact["kind"]))
            self.db.execute("UPDATE jobs SET state='succeeded',stage='Completed',metadata=?,error='',updated=? WHERE id=?",
                            (json.dumps(manifest["metadata"]), now(), job_id))

    def recover(self):
        for job in self.jobs():
            if job["state"] in {"running", "queued"}:
                manifest = owned_path(self.job_dir(job["id"]), "result/manifest.json")
                if manifest.is_file():
                    try:self.complete(job["id"])
                    except (OSError,ValueError) as error:
                        self.update(job['id'],'failed','Failed',f'Could not save conversion outputs: {error}')
                else:
                    clean_staging(self.job_dir(job["id"]))
                    self.update(job["id"], "interrupted", "Interrupted", "The app stopped before conversion finished. Retry to start again.")

    def remove_history(self, job_id: str):
        if self.get(job_id)["state"] in {"queued", "running"}:
            raise ValueError("Cancel this conversion first")
        with self.db:
            self.db.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    def delete_outputs(self, job_id: str, trash=None):
        from send2trash import send2trash
        if self.get(job_id)["state"] in {"queued", "running"}:
            raise ValueError("Cancel this conversion first")
        trash = trash or send2trash
        root = self.job_dir(job_id)
        artifacts = [row for row in self.artifacts(job_id) if not row["deleted"]]
        # Validate every target before touching any file. Only delete recorded files.
        targets = [(row,self.artifact_path(job_id,row),owned_path(root,row['path'])) for row in artifacts]
        for row, path, internal in targets:
            for target in dict.fromkeys((path,internal)):
                if target.exists():trash(str(target))
            with self.db:
                self.db.execute("UPDATE artifacts SET deleted=1 WHERE job_id=? AND path=?", (job_id, row["path"]))
