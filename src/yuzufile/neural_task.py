"""Isolated ONNX stage: exit releases native heaps before loading a VLM."""
import json
import os
from pathlib import Path
import subprocess
import sys


def run(kind, images, languages, threads):
    command = ([str(Path(sys.executable).with_name('yuzufile-worker.exe')), '--neural-task']
               if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'yuzufile.neural_task'])
    request = dict(kind=kind, images=[str(p) for p in images], languages=languages, threads=threads)
    environment = os.environ.copy()
    if kind == 'indra':
        environment['HF_HUB_OFFLINE'] = '1'
        environment['HF_HUB_DISABLE_TELEMETRY'] = '1'
    result = subprocess.run(command, input=json.dumps(request), text=True, encoding='utf-8',
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600, env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise RuntimeError(f'{kind} stage stopped (exit {result.returncode}). ' + result.stderr[-300:])
    return json.loads(result.stdout)


def main():
    import contextlib
    import logging
    logging.disable(logging.CRITICAL)
    request = json.load(sys.stdin)
    protocol = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        if request['kind'] == 'indra':
            from yuzufile.indra_engine import Reader
            reader = Reader(request['threads'], request['languages'])
            result = [reader.read(Path(p)) for p in request['images']]
        elif request['kind'] == 'rapid':
            from yuzufile.neural_text import RapidReader
            reader = RapidReader(request['languages'], request['threads'])
            result = [reader.read(Path(p)) for p in request['images']]
        elif request['kind'] == 'layout':
            from yuzufile.neural_markdown import layout_reader
            reader = layout_reader(request['threads'])
            result = []
            for path in request['images']:
                output = reader(Path(path))
                result.append([list(map(float, box)) for box, kind in zip(output.boxes, output.class_names)
                               if 'table' in kind.lower()])
        else:
            raise ValueError('Unknown neural stage.')
    # JSON escapes keep the helper protocol portable across Windows console
    # encodings; decoding restores the original multilingual Unicode text.
    print(json.dumps(result, ensure_ascii=True), file=protocol, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
