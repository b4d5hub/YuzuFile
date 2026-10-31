"""Resolve worker outputs through their public manifest rather than filenames."""
import json
from pathlib import Path


def artifact_paths(root,kind):
    root=Path(root)
    result=root if root.name=='result' else root/'result'
    manifest=json.loads((result/'manifest.json').read_text(encoding='utf-8'))
    paths=[result.parent/entry['path'] for entry in manifest['artifacts'] if entry['kind']==kind]
    assert all(path.is_file() for path in paths)
    return paths


def artifact_path(root,kind):
    paths=artifact_paths(root,kind)
    assert len(paths)==1,(kind,paths)
    return paths[0]
