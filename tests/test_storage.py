import json
import os
import subprocess
from pathlib import Path

import pytest

from yuzufile.storage import Store, owned_path


def test_custom_output_records_destination_and_never_overwrites(store, digital_pdf, tmp_path):
    destination = tmp_path / 'Exports with spaces'
    destination.mkdir()
    original = digital_pdf.read_bytes()
    existing = destination / 'document.md'
    existing.write_text('Keep this')
    first = store.create(digital_pdf, 'markdown', [], output_directory=destination)
    second = store.create(digital_pdf, 'markdown', [], output_directory=destination)
    assert store.job_dir(first) != store.job_dir(second)
    assert store.job_dir(first).parent == destination
    root = publish(store, first)
    (root / 'result/assets').mkdir()
    (root / 'result/assets/figure.png').write_bytes(b'image')
    manifest_path = root / 'result/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['artifacts'].append({'path': 'result/assets/figure.png', 'kind': 'asset'})
    manifest_path.write_text(json.dumps(manifest))
    store.complete(first)
    extra = root / 'result/keep.txt'
    extra.write_text('User file')
    # Query a new connection to confirm the destination is durable without
    # closing the fixture's store or sharing an instance lock.
    import sqlite3
    with sqlite3.connect(store.home / 'history.sqlite3') as db:
        assert db.execute('SELECT output_directory FROM jobs WHERE id=?', (first,)).fetchone()[0] == str(destination)
    store.delete_outputs(first, trash=lambda path: Path(path).unlink())
    assert not (root / 'result/document.md').exists()
    assert not (root / 'result/assets/figure.png').exists()
    assert extra.read_text() == 'User file'
    assert existing.read_text() == 'Keep this'
    assert digital_pdf.read_bytes() == original


def test_custom_output_rejects_missing_or_unwritable_folder(store, digital_pdf, tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='no longer available'):
        store.create(digital_pdf, 'markdown', [], output_directory=tmp_path / 'missing')
    destination = tmp_path / 'readonly'
    destination.mkdir()
    original_open = Path.open
    def deny_probe(path, *args, **kwargs):
        if path.name.startswith('.yuzufile-write-check-'):
            raise PermissionError('Test fixture')
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', deny_probe)
    with pytest.raises(ValueError, match='Cannot write'):
        store.create(digital_pdf, 'markdown', [], output_directory=destination)
    assert not store.jobs()
    assert not list(destination.iterdir())


def test_custom_output_disappearing_before_start_fails_cleanly(store, digital_pdf, tmp_path):
    from yuzufile.supervisor import Supervisor
    destination = tmp_path / 'removed'
    destination.mkdir()
    job = store.create(digital_pdf, 'markdown', [], output_directory=destination)
    destination.rmdir()
    supervisor = Supervisor(store)
    supervisor.tick()
    assert store.get(job)['state'] == 'failed'
    assert 'output folder is no longer available' in store.get(job)['error']
    assert supervisor.process is None


def publish(store, job_id):
    root = store.job_dir(job_id)
    (root / "result").mkdir(parents=True)
    (root / "result/document.md").write_text("Hello", encoding="utf-8")
    (root / "result/manifest.json").write_text(json.dumps({
        "artifacts": [{"path": "result/document.md", "kind": "markdown"}], "metadata": {"pages": 1}
    }), encoding="utf-8")
    return root


def test_history_survives_restart_and_no_saved_language_defaults(tmp_path, digital_pdf):
    home = tmp_path / "home"
    store = Store(home)
    destination = tmp_path / "Chosen output folder"
    destination.mkdir()
    first = store.create(digital_pdf, "both", ["eng", "fra"], output_directory=destination)
    second = store.create(digital_pdf, "markdown", [])
    store.close()
    reopened = Store(home)
    try:
        assert json.loads(reopened.get(first)["languages"]) == ["eng", "fra"]
        assert json.loads(reopened.get(second)["languages"]) == []
        assert reopened.job_dir(first).parent == destination
        assert reopened.job_dir(second).parent == reopened.library
    finally:
        reopened.close()


def test_second_instance_cannot_recover_active_library(store):
    with pytest.raises(ValueError, match="already using"):
        Store(store.home)


def test_crash_recovery_registers_published_outputs_and_cleans_partial(store, digital_pdf):
    published = store.create(digital_pdf, "markdown", [])
    publish(store, published)
    store.update(published, "running", "Working")
    partial = store.create(digital_pdf, "both", ["eng"])
    staging = store.job_dir(partial) / "staging"
    staging.mkdir(parents=True)
    (staging / "input.pdf").write_bytes(b"private snapshot")
    store.recover()
    assert store.get(published)["state"] == "succeeded"
    assert store.get(partial)["state"] == "interrupted"
    assert not staging.exists()


def test_delete_targets_only_outputs_and_keeps_source(store, digital_pdf):
    original = digital_pdf.read_bytes()
    job = store.create(digital_pdf, "markdown", [])
    root = publish(store, job)
    extra = root / "result/keep.txt"
    extra.write_text("unrecorded")
    store.complete(job)
    deleted = []
    def trash(path):
        deleted.append(Path(path))
        Path(path).unlink()
    store.delete_outputs(job, trash=trash)
    assert deleted == [digital_pdf.parent/'document.md',root / "result/document.md"]
    assert digital_pdf.read_bytes() == original
    assert extra.exists()
    assert store.artifacts(job)[0]["deleted"]
    store.remove_history(job)
    assert extra.exists()


def test_remove_history_keeps_outputs(store, digital_pdf):
    job = store.create(digital_pdf, "markdown", [])
    root = publish(store, job)
    store.complete(job)
    store.remove_history(job)
    assert (root / "result/document.md").exists()


def test_partial_deletion_keeps_truthful_artifact_state(store, digital_pdf):
    job = store.create(digital_pdf, "markdown", [])
    publish(store, job)
    store.complete(job)
    def locked(path):
        raise PermissionError("locked")
    with pytest.raises(PermissionError):
        store.delete_outputs(job, trash=locked)
    assert not store.artifacts(job)[0]["deleted"]


@pytest.mark.parametrize("relative", ["../source.pdf", "/outside/file", "result/../../secret"])
def test_rejects_outside_paths(tmp_path, relative):
    with pytest.raises(ValueError):
        owned_path(tmp_path, relative)


def test_junction_does_not_allow_deletion_outside_library(store, digital_pdf, tmp_path):
    job = store.create(digital_pdf, "markdown", [])
    root = publish(store, job)
    store.complete(job)
    # Replace the result directory with a junction (Windows) or symlink (Unix).
    result = root / "result"
    result.rename(root / "saved-result")
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "document.md"
    victim.write_text("must survive")
    if os.name == "nt":
        process = subprocess.run(["cmd", "/c", "mklink", "/J", str(result), str(outside)], capture_output=True)
        assert process.returncode == 0
    else:
        result.symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="links|junctions"):
            store.delete_outputs(job, trash=lambda path: Path(path).unlink())
        assert victim.read_text() == "must survive"
    finally:
        if os.name == "nt":
            result.rmdir()
        else:
            result.unlink()

