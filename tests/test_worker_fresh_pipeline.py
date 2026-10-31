"""Real export objects must be built from fresh OCR, never an old PDF layer."""
import json
from pathlib import Path
import pymupdf,pytest
from PIL import Image
from docx import Document
from yuzufile.worker import convert
from yuzufile.operations import mode_for
from artifact_helpers import artifact_path


@pytest.fixture
def fresh_source(tmp_path):
    path=tmp_path/'Old OCR layer.pdf'
    with pymupdf.open() as doc:
        for index in range(3):
            p=doc.new_page(width=300,height=420)
            p.insert_text((30,65),f'VISIBLE PAGE {index+1}',fontsize=22)
            p.insert_text((30,100),'OLD WRONG HIDDEN TEXT',render_mode=3)
            doc.xref_set_key(p.xref,'PDFaiOCR','true')
        doc.save(path)
    return path


@pytest.fixture
def controlled_ocr(monkeypatch):
    events=[]
    monkeypatch.setattr('yuzufile.worker.installed_languages',lambda:['eng'])
    monkeypatch.setattr('yuzufile.neural_text.available',lambda:False)
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:False)
    monkeypatch.setattr('yuzufile.vision_runtime.available',lambda:False)
    def recognize(image,dpi,languages,number):
        events.append(('ocr',number))
        with Image.open(image) as raster:
            assert min(raster.convert('L').getextrema())<100
            width,height=raster.size
        output=image.with_suffix('.ocr.json')
        output.write_text(json.dumps(dict(width=width,height=height,engine='Controlled visual OCR',
            rows=[dict(text=f'FRESH PAGE {number}',box=[70,100,650,155],score=.99)])))
        return output
    monkeypatch.setattr('yuzufile.engines.recognize_page',recognize)
    from yuzufile import word_export
    paragraph=word_export._paragraph
    def capture(parent,spans,*args,**kwargs):
        text=''.join(span.get('text','') for span in spans)
        if 'FRESH PAGE' in text:events.append(('word',int(text.split('FRESH PAGE ')[1].split()[0])))
        return paragraph(parent,spans,*args,**kwargs)
    monkeypatch.setattr(word_export,'_paragraph',capture)
    return events


def test_word_cleans_recognizes_and_builds_each_page_before_next(fresh_source,tmp_path,controlled_ocr):
    root=tmp_path/'word-job'
    convert(dict(root=str(root),source=str(fresh_source),mode=mode_for({'ocr','markdown','docx'}),languages=['eng'],performance='high'))
    assert controlled_ocr==[('ocr',1),('word',1),('ocr',2),('word',2),('ocr',3),('word',3)]
    with pymupdf.open(artifact_path(root,'pdf')) as doc:
        assert all('OLD WRONG' not in p.get_text() and 'VISIBLE PAGE' not in p.get_text() for p in doc)
        assert [p.get_text().strip() for p in doc]==['FRESH PAGE 1','FRESH PAGE 2','FRESH PAGE 3']
    word=Document(artifact_path(root,'docx'));text='\n'.join(p.text for p in word.paragraphs)
    assert all(f'FRESH PAGE {n}' in text for n in (1,2,3)) and 'OLD WRONG' not in text
    assert len(word.sections)==3
    markdown=artifact_path(root,'markdown').read_text(encoding='utf-8')
    assert all(f'FRESH PAGE {n}' in markdown for n in (1,2,3)) and 'OLD WRONG' not in markdown
    manifest=json.loads((root/'result/manifest.json').read_text());data=manifest['metadata']
    assert data['ocr_pages']==3 and data['reused_pages']==0 and data['page_workers']==1
    assert data['text_preparation']['old_text_reused'] is False
    assert data['word']['fresh_ocr_pages']==3
    assert not (root/'staging').exists()


@pytest.mark.parametrize('mode',['pdf','markdown','word'])
def test_even_native_pdf_requires_languages_for_new_fresh_policy(fresh_source,tmp_path,mode):
    from yuzufile.engines import ConversionError
    with pytest.raises(ConversionError,match='language'):
        convert(dict(root=str(tmp_path/mode),source=str(fresh_source),mode=mode,languages=[],performance='low'))
    assert not (tmp_path/mode/'result').exists()
    assert not (tmp_path/mode/'staging').exists()


def test_page_two_recognition_failure_never_publishes_partial_word(fresh_source,tmp_path,controlled_ocr,monkeypatch):
    from yuzufile.engines import ConversionError
    from yuzufile import engines
    previous=engines.recognize_page
    def failing(image,dpi,languages,number):
        if number==2:raise ConversionError('Recognition could not finish page 2')
        return previous(image,dpi,languages,number)
    monkeypatch.setattr(engines,'recognize_page',failing)
    root=tmp_path/'failed-word'
    with pytest.raises(ConversionError,match='page 2'):
        convert(dict(root=str(root),source=str(fresh_source),mode='word',languages=['eng'],performance='high'))
    assert not (root/'result').exists() and not (root/'staging').exists()
