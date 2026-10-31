"""Explicit model acquisition for an authorized personal-use build."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REVISION = 'bd02167fdf2005a19962cc15188f8496a2c87d3b'
FILES = ('LICENSE', 'det.onnx', 'rec.onnx', 'order.onnx', 'meta.json',
         'orient.onnx', 'script.onnx', 'rec_rtl.onnx', 'rec_cjk.onnx',
         'rec_world.onnx', 'lm.npz', 'lm_cjk.npz', 'lm_world.npz')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--personal-use', action='store_true', required=True,
        help='The build is for personal use; review the restricted model license before distribution.')
    parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'vendor/neural/indra'
    root.mkdir(parents=True, exist_ok=True)
    records = {}
    for name in FILES:
        target = root / name
        if not target.is_file():
            partial = root / (name + '.partial')
            try:
                with urllib.request.urlopen(f'https://huggingface.co/datalab-to/indra-ocr/resolve/{REVISION}/{name}', timeout=120) as source, partial.open('wb') as out:
                    while chunk := source.read(1024 * 1024):
                        out.write(chunk)
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        with target.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        records[name] = dict(sha256=digest, bytes=target.stat().st_size)
        print(name, target.stat().st_size, flush=True)
    (root / 'ready.json').write_text(json.dumps(dict(package='1.1.2',
        model_revision=REVISION, personal_use=True, files=records), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
