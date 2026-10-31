"""Verify actual OS process-tree cleanup when the owning app crashes."""
import json
import os
import subprocess
import sys
import time

import psutil
import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object lifecycle")
def test_app_crash_stops_worker_and_grandchild(tmp_path):
    runner = tmp_path / "job_owner.py"
    runner.write_text('''
import json, subprocess, sys
from yuzufile.windows_job import WindowsJob
group = WindowsJob()
child_code = "import subprocess, sys; sys.stdin.readline(); p=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); print(p.pid, flush=True); sys.stdin.readline()"
child = subprocess.Popen([sys.executable, '-c', child_code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
group.assign(child)
child.stdin.write('go\\n'); child.stdin.flush()
grandchild = int(child.stdout.readline())
print(json.dumps([child.pid, grandchild]), flush=True)
sys.stdin.readline()
''', encoding="utf-8")
    owner = subprocess.Popen([sys.executable, str(runner)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    descendants = []
    try:
        line = owner.stdout.readline()
        assert line, owner.stderr.read()
        descendants = json.loads(line)
        assert all(psutil.pid_exists(pid) for pid in descendants)
        owner.kill()
        owner.wait(timeout=10)
        deadline = time.monotonic() + 5
        while any(psutil.pid_exists(pid) for pid in descendants) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not any(psutil.pid_exists(pid) for pid in descendants)
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=10)
        for pipe in (owner.stdin, owner.stdout, owner.stderr):
            pipe.close()
        for pid in descendants:
            if psutil.pid_exists(pid):
                psutil.Process(pid).kill()
