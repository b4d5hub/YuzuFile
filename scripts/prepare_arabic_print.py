"""Explicit, checksum-verified acquisition of the offline Arabic print model."""
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    project = Path(__file__).resolve().parents[1]
    manifest_path = project / 'docs/arabic-print-model.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    root = project / 'vendor/neural/arabic-print'
    root.mkdir(parents=True, exist_ok=True)
    for name, record in manifest['files'].items():
        target = root / name
        def valid(path):
            if not path.is_file() or path.stat().st_size != record['bytes']:
                return False
            with path.open('rb') as stream:
                return hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256']
        if not valid(target):
            partial = target.with_suffix('.partial')
            url = (f"https://huggingface.co/{manifest['repository']}/resolve/{manifest['revision']}/"
                   f"models/squiddle_PP-OCRv6_medium_rec/{name}?download=true")
            try:
                with urllib.request.urlopen(url, timeout=120) as source, partial.open('wb') as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                if not valid(partial):
                    raise RuntimeError(f'Arabic print model checksum mismatch: {name}')
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        print('Verified:', name, flush=True)
    (root / 'ready.json').write_text(manifest_path.read_text(encoding='utf-8'), encoding='utf-8')


if __name__ == '__main__':
    main()
