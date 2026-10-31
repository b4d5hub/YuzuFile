import json
from pathlib import Path
from urllib.parse import unquote
import pytest


def finish(store,job,markdown=False):
    root=store.job_dir(job)/'result';root.mkdir(parents=True)
    name='book_markdown.md' if markdown else 'book_compress.pdf'
    (root/name).write_text('![figure](assets/figure.png)\nhttps://example.com/assets/info' if markdown else 'PDF fixture',encoding='utf-8')
    artifacts=[{'path':'result/'+name,'kind':'markdown' if markdown else 'pdf'}]
    if markdown:
        (root/'assets').mkdir();(root/'assets/figure.png').write_bytes(b'image')
        artifacts.append({'path':'result/assets/figure.png','kind':'asset'})
    (root/'manifest.json').write_text(json.dumps({'artifacts':artifacts,'metadata':{}}))
    store.complete(job)
    return store.artifact_path(job,artifacts[0])


def test_batch_saves_to_each_original_folder_and_preserves_sources(store,digital_pdf,tmp_path):
    folder=tmp_path/'Another folder';folder.mkdir()
    other=folder/'Arabic العربية.pdf';other.write_bytes(digital_pdf.read_bytes())
    original=digital_pdf.read_bytes()
    first=store.create(digital_pdf,'compress',[]);second=store.create(other,'compress',[])
    assert finish(store,first).parent==digital_pdf.parent
    assert finish(store,second).parent==other.parent
    assert digital_pdf.read_bytes()==original and other.read_bytes()==original
    assert store.get(first)['output_directory']==''


def test_existing_results_are_not_overwritten_and_completion_is_idempotent(store,digital_pdf):
    existing=digital_pdf.parent/'book_compress.pdf';existing.write_bytes(b'keep')
    job=store.create(digital_pdf,'compress',[])
    output=finish(store,job)
    assert output.name=='book_compress (2).pdf' and existing.read_bytes()==b'keep'
    store.complete(job)
    assert not (output.parent/'book_compress (3).pdf').exists()


def test_manual_destination_still_takes_priority(store,digital_pdf,tmp_path):
    chosen=tmp_path/'Chosen';chosen.mkdir()
    job=store.create(digital_pdf,'compress',[],output_directory=chosen)
    output=finish(store,job)
    assert output.is_relative_to(chosen) and output.is_file()
    assert not (digital_pdf.parent/'book_compress.pdf').exists()


def test_markdown_figures_remain_linked_and_open_folder_is_source_folder(store,digital_pdf):
    job=store.create(digital_pdf,'markdown',[])
    output=finish(store,job,markdown=True)
    text=output.read_text(encoding='utf-8')
    link=text.split('](')[1].split(')')[0]
    assert 'https://example.com/assets/info' in text
    assert (output.parent/unquote(link)).read_bytes()==b'image'
    assert store.result_directory(job)==digital_pdf.parent


def test_old_history_paths_remain_unchanged(store,digital_pdf):
    job=store.create(digital_pdf,'compress',[])
    store.db.execute('UPDATE jobs SET save_beside_source=0 WHERE id=?',(job,));store.db.commit()
    output=finish(store,job)
    assert output==store.job_dir(job)/'result/book_compress.pdf'


def test_default_folder_is_checked_before_queueing(store,digital_pdf,monkeypatch):
    original=Path.open
    def deny(path,*args,**kwargs):
        if path.name.startswith('.yuzufile-write-check-'):raise PermissionError('read-only')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',deny)
    with pytest.raises(ValueError,match='Cannot write'):store.create(digital_pdf,'compress',[])
    assert not store.jobs()
