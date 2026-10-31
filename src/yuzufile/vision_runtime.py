"""Local, sequential GGUF inference. Never contacts a hosted inference service."""
from contextlib import AbstractContextManager
import base64
import json
import os
from pathlib import Path
import socket
import secrets
import subprocess
import time
import urllib.error
import urllib.request

from yuzufile.neural_text import model_root


def available():
    root = model_root()
    return all((root / name).is_file() for name in (
        'runtime/llama-server.exe', 'paddle/model.gguf', 'paddle/mmproj.gguf',
        'lighton/model.gguf', 'lighton/mmproj.gguf', 'layout/pp_doc_layoutv3.onnx'))


class VisionRuntime(AbstractContextManager):
    def __init__(self, engine, scratch: Path, threads=2,context_size=8192):
        self.engine, self.scratch, self.threads = engine, scratch, threads
        self.process = self.log = None
        self.context_size=max(1024,min(8192,int(context_size)))
        self.token = secrets.token_urlsafe(32)
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def __enter__(self):
        root = model_root()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.log = (self.scratch / f'{self.engine}-runtime.log').open('wb')
        command = [str(root / 'runtime/llama-server.exe'),
            '-m', str(root / self.engine / 'model.gguf'),
            '--mmproj', str(root / self.engine / 'mmproj.gguf'),
            '--host', '127.0.0.1', '--port', str(port), '--ctx-size', str(self.context_size),
            '--threads', str(self.threads), '--threads-batch', str(self.threads),
            '--parallel', '1', '--n-gpu-layers', '0', '--no-mmproj-offload',
            '--no-webui', '--reasoning', 'off', '--alias', 'yuzufile', '--api-key', self.token]
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                stdout=self.log, stderr=self.log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    self.log.flush()
                    details = (self.scratch / f'{self.engine}-runtime.log').read_text(encoding='utf-8', errors='replace')[-1500:]
                    raise RuntimeError(f'{self.engine} failed (exit {self.process.returncode}): {details}')
                try:
                    health = urllib.request.Request(self.url + '/health', headers={'Authorization': 'Bearer ' + self.token})
                    with self.client.open(health, timeout=2) as response:
                        if response.status == 200:
                            return self
                except (OSError, urllib.error.URLError):
                    time.sleep(.25)
            raise RuntimeError(f'{self.engine} model loading timed out.')
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def recognize(self, image: Path, prompt: str, max_tokens=4096):
        content = base64.b64encode(image.read_bytes()).decode('ascii')
        payload = {'model': 'yuzufile', 'messages': [{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + content}},
            {'type': 'text', 'text': prompt}]}], 'max_tokens': max_tokens,
            'temperature': 0, 'stream': False}
        request = urllib.request.Request(self.url + '/v1/chat/completions',
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.token})
        with self.client.open(request, timeout=600) as response:
            result = json.load(response)
        choice = result['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise RuntimeError(f'{self.engine} reached its output limit; the region needs splitting.')
        return choice['message'].get('content') or ''

    def __exit__(self, *args):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        if self.log is not None:
            self.log.close()
        return False
