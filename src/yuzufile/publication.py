"""Publish default outputs beside their original, without overwriting files."""
import json
import os
import shutil
from pathlib import Path
from urllib.parse import quote


def publish_beside_source(root, source, job_id, artifacts):
    from yuzufile.storage import owned_path
    root, destination = Path(root), Path(source).parent
    receipt = owned_path(root, 'publication.json')
    if receipt.is_file():
        return json.loads(receipt.read_text(encoding='utf-8'))
    primary = {'pdf', 'docx', 'markdown', 'report'}
    companions = [a for a in artifacts if a['kind'] not in primary]
    folder = f'{Path(source).stem[:80]}_assets_{job_id[:8]}'
    created, directory, mapping = [], None, {}
    try:
        if companions:
            candidate_directory = owned_path(destination, folder)
            candidate_directory.mkdir()
            directory = candidate_directory
        for artifact in artifacts:
            relative = artifact['path']
            original = owned_path(root, relative)
            if artifact['kind'] not in primary:
                target_relative = str(Path(folder) / Path(relative).relative_to('result'))
                target = owned_path(destination, target_relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as output, original.open('rb') as input_file:
                    created.append(target)
                    shutil.copyfileobj(input_file, output)
            else:
                name = original.name
                for number in range(1, 100001):
                    candidate = name if number == 1 else f'{original.stem} ({number}){original.suffix}'
                    target = owned_path(destination, candidate)
                    try:
                        output = target.open('xb')
                    except FileExistsError:
                        continue
                    created.append(target)
                    with output:
                        if artifact['kind'] == 'markdown' and companions:
                            text = original.read_text(encoding='utf-8')
                            for prefix in ('](', '](<', 'src="', "src='"):
                                text = text.replace(prefix+'assets/', prefix+quote(folder, safe='')+'/assets/')
                            for item in companions:
                                old = str(Path(item['path']).relative_to('result')).replace('\\', '/')
                                if not old.startswith('assets/'):
                                    text = text.replace(']('+old+')', ']('+quote(folder, safe='')+'/'+old+')')
                            output.write(text.encode('utf-8'))
                        else:
                            with original.open('rb') as input_file:shutil.copyfileobj(input_file, output)
                    break
                else:raise ValueError('Too many files with the same output name. Choose another folder.')
                target_relative = target.name
            mapping[relative] = target_relative
        temporary = owned_path(root, 'publication.tmp')
        temporary.write_text(json.dumps(mapping), encoding='utf-8')
        temporary.replace(receipt)
        return mapping
    except Exception:
        for target in reversed(created):
            if target.is_file() and not target.is_symlink():target.unlink()
        if directory is not None:
            # Only this attempt's exclusively-created companion directory.
            checked = owned_path(destination, folder)
            if checked.is_dir():
                for parent,dirs,files in os.walk(checked,topdown=False):
                    try:Path(parent).rmdir()
                    except OSError:pass
        raise
