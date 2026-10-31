from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from yuzufile.storage import Store, owned_path, clean_staging
from yuzufile.windows_job import WindowsJob
from yuzufile.performance import performance_profile


class Supervisor:
    """Main-thread database owner; background thread only drains process events."""
    def __init__(self, store: Store):
        self.store = store
        self.process = None
        self.active = None
        self.events = queue.Queue()
        self.reader = None
        self.last_error = ""
        self.started = 0
        self.process_group = None
        self.progress = 0
        self.last_finished = None

    def tick(self):
        changed = False
        if self.process and time.monotonic() - self.started > 86400:
            job_id = self.active
            self.cancel(job_id)
            if self.store.get(job_id)["state"] != "succeeded":
                self.store.update(job_id, "failed", "Timed out", "Conversion exceeded the 24-hour processing limit.")
            changed = True
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if self.active:
                self.last_error = event.get("error", self.last_error)
                self.progress = max(self.progress, event.get("progress", self.progress))
                self.store.update(self.active, "running", event.get("stage", "Working"))
                changed = True
        if self.process and self.process.poll() is not None and not self.reader.is_alive():
            # Reader may have enqueued its last event after the loop above.
            while not self.events.empty():
                event = self.events.get_nowait()
                self.last_error = event.get("error", self.last_error)
            job_id = self.active
            self.last_finished = job_id
            if self.process.returncode == 0:
                try:
                    self.store.complete(job_id)
                except Exception as error:
                    self.store.update(job_id, "failed", "Failed", f"Could not save conversion outputs: {error}")
            else:
                self.store.update(job_id, "failed", "Failed", self.last_error or "The conversion worker stopped unexpectedly.")
            self.process.stdout.close()
            self.process_group.close()
            self.process_group = None
            clean_staging(self.store.job_dir(job_id))
            self.process = None
            self.active = None
            changed = True
        if self.process is None:
            queued = [job for job in reversed(self.store.jobs()) if job["state"] == "queued"]
            if queued:
                self._start(queued[0])
                changed = True
        return changed

    def _start(self, job):
        job_id = job["id"]
        self.active = job_id
        self.last_error = ""
        self.started = time.monotonic()
        self.progress = 0
        self.store.update(job_id, "running", "Starting conversion")
        command = [str(Path(sys.executable).with_name("yuzufile-worker.exe")), "--worker"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "yuzufile", "--worker"]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + environment.get("PYTHONPATH", "")
        environment["PYTHONIOENCODING"] = "utf-8"
        profile = performance_profile(job.get("performance", "balanced"))
        environment.update(profile.environment())
        try:
            if job.get("output_directory") and not Path(job["output_directory"]).is_dir():
                raise ValueError("The output folder is no longer available. Choose another folder and retry.")
            self.process_group = WindowsJob(memory_mb=profile.memory_mb, cpu_percent=profile.cpu_percent)
            self.process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            # The worker blocks on stdin until it belongs to the kill-on-close job.
            self.process_group.assign(self.process)
            request = {"source": job["source"], "mode": job["mode"],
                       "split_settings": json.loads(job["split_settings"]),
                       "page_plan": json.loads(job['page_plan']),
                       'cleanup_settings': json.loads(job['cleanup_settings']),
                       "compression": job["compression"], "performance": profile.code,
                       "languages": json.loads(job["languages"]), "root": str(self.store.job_dir(job_id))}
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.close()
            self.reader = threading.Thread(target=self._read, args=(self.process,), daemon=True)
            self.reader.start()
        except (OSError, ValueError) as error:
            if self.process:
                self.process.kill()
                self.process.wait()
                self.process.stdout.close()
            if self.process_group:
                self.process_group.close()
                self.process_group = None
            self.process = None
            self.active = None
            self.store.update(job_id, "failed", "Failed", str(error) if isinstance(error, ValueError)
                              else f"Could not start conversion ({type(error).__name__}).")

    def _read(self, process):
        for line in process.stdout:
            try:
                event = json.loads(line)
                if isinstance(event, dict) and event.get("version") == 1:
                    self.events.put(event)
            except (ValueError, TypeError):
                pass

    def cancel(self, job_id):
        job = self.store.get(job_id)
        if job["state"] not in {"queued", "running"}:
            return
        if job_id == self.active and self.process:
            if os.name == "nt":
                self.process_group.close()
            else:
                self._kill_tree()
            self.process.wait(timeout=10)
            self.reader.join(timeout=5)
            self.process.stdout.close()
            self.process_group.close()
            self.process_group = None
            self.process = None
            self.active = None
            while not self.events.empty():
                self.events.get_nowait()
        root = self.store.job_dir(job_id)
        clean_staging(root)
        # If completion won the race, register valid outputs rather than hide them.
        if owned_path(root, "result/manifest.json").exists():
            self.store.complete(job_id)
        else:
            self.store.update(job_id, "cancelled", "Cancelled")

    def _kill_tree(self):
        try:
            parent = psutil.Process(self.process.pid)
            children = parent.children(recursive=True)
            parent.suspend()  # Prevent spawning more children during termination.
            for child in reversed(children):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            parent.kill()
            psutil.wait_procs(children, timeout=3)
        except psutil.NoSuchProcess:
            pass

    def shutdown(self):
        for job in self.store.jobs():
            if job["state"] in {"queued", "running"}:
                self.cancel(job["id"])
