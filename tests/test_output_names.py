"""Published names retain source names and distinguish generated documents."""
import hashlib,json
from pathlib import Path
import pymupdf
import pytest
from yuzufile.output_names import output_name,rename_outputs
from yuzufile.worker import convert


@pytest.mark.parametrize('operations,kind,expected',[
    ({'ocr'},'pdf','Report.v2_ocr.pdf'),
    ({'markdown'},'markdown','Report.v2_markdown.md'),
    ({'docx'},'docx','Report.v2_word.docx'),
    ({'compress'},'pdf','Report.v2_compress.pdf'),
    ({'split'},'pdf','Report.v2_split.pdf'),
    ({'cleanup'},'pdf','Report.v2_cleanup.pdf'),
    ({'organize'},'pdf','Report.v2_arrange.pdf'),
    ({'remove_ocr'},'pdf','Report.v2_remove_ocr.pdf'),
    ({'ocr','compress','markdown','docx'},'pdf','Report.v2_ocr_compress.pdf'),
    ({'cleanup','split','ocr','compress','markdown','docx'},'docx','Report.v2_cleanup_split_word.docx'),
    ({'cleanup','split','ocr','compress','markdown','docx'},'markdown','Report.v2_cleanup_split_markdown.md'),
    ({'split','remove_ocr','compress'},'pdf','Report.v2_split_remove_ocr_compress.pdf'),
    ({'docx'},'report','Report.v2_word.quality.json'),
])
def test_document_names_describe_the_operations_in_that_output(operations,kind,expected):
    assert output_name(Path('Report.v2.PDF'),operations,kind)==expected


def test_source_spaces_arabic_case_and_long_windows_names_are_retained():
    assert output_name('Résumé كتاب 2.pdf',{'ocr'},'pdf')=='Résumé كتاب 2_ocr.pdf'
    name=output_name('كتاب'*90+'.pdf',{'remove_ocr','compress'},'pdf')
    assert name.endswith('_remove_ocr_compress.pdf') and len(name.encode('utf-16-le'))//2<=255


def test_publish_keeps_markdown_assets_and_names_word_report_together(tmp_path):
    (tmp_path/'assets').mkdir();(tmp_path/'assets/figure.png').write_bytes(b'figure')
    body='# Text\n![Figure](assets/figure.png)\n'
    for name,text in [('document.md',body),('document.docx','word'),('document.quality.json','{}'),('INDRA-NOTICE.txt','license')]:
        (tmp_path/name).write_text(text,encoding='utf-8')
    artifacts=[dict(path='result/'+name,kind=kind) for name,kind in [
        ('document.md','markdown'),('document.docx','docx'),('document.quality.json','report'),
        ('assets/figure.png','asset'),('INDRA-NOTICE.txt','license')]]
    named=rename_outputs(tmp_path,'My book.pdf',{'markdown','docx'},artifacts)
    assert [a['path'] for a in named]==[
        'result/My book_markdown.md','result/My book_word.docx','result/My book_word.quality.json',
        'result/assets/figure.png','result/INDRA-NOTICE.txt']
    assert (tmp_path/'My book_markdown.md').read_text()==body
    assert all((tmp_path/Path(a['path']).relative_to('result')).is_file() for a in named)
    assert artifacts[0]['path']=='result/document.md'


def test_existing_output_is_never_overwritten(tmp_path):
    (tmp_path/'document.md').write_text('new')
    (tmp_path/'Report_markdown.md').write_text('existing')
    with pytest.raises(ValueError,match='already in use'):
        rename_outputs(tmp_path,'Report.pdf',{'markdown'},[dict(path='result/document.md',kind='markdown')])
    assert (tmp_path/'Report_markdown.md').read_text()=='existing'
    assert (tmp_path/'document.md').read_text()=='new'


@pytest.mark.parametrize('mode,suffix',[('remove_ocr','remove_ocr'),('remove_ocr_compress','remove_ocr_compress')])
def test_real_worker_and_manifest_use_original_arabic_filename(tmp_path,mode,suffix):
    source=tmp_path/'Mon livre كتاب.pdf'
    with pymupdf.open() as document:
        document.new_page().insert_text((40,80),'Visible text');document.save(source)
    digest=hashlib.sha256(source.read_bytes()).digest()
    root=tmp_path/'job'
    convert(dict(root=str(root),source=str(source),mode=mode,languages=[],compression='lossless',performance='low'))
    manifest=json.loads((root/'result/manifest.json').read_text())
    pdf=next(a for a in manifest['artifacts'] if a['kind']=='pdf')
    assert pdf['path']==f'result/Mon livre كتاب_{suffix}.pdf'
    with pymupdf.open(root/pdf['path']) as result:
        assert len(result)==1 and not result[0].get_text().strip()
    assert not list((root/'result').glob('document.*'))
    assert hashlib.sha256(source.read_bytes()).digest()==digest
