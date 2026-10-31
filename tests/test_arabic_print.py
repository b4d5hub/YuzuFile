"""CTC, mixed-script ordering and offline Arabic recognizer contracts."""
import numpy as np
import pytest
from yuzufile import arabic_ocr


def test_ctc_collapses_before_bidi_and_preserves_diacritics():
    from bidi.algorithm import get_display
    text='٣ - نَوَاقِضُ الإِسْلَامِ'
    visual=get_display(text,base_dir='R')
    characters=['']+list(dict.fromkeys(visual))
    ids=[]
    for char in visual:
        ids.extend([characters.index(char),characters.index(char),0])
    matrix=np.zeros((len(ids),len(characters)),dtype=np.float32)
    matrix[np.arange(len(ids)),ids]=1
    decoded,confidence=arabic_ocr.decode_ctc(matrix,characters)
    assert decoded==text
    assert confidence==1


def test_ctc_does_not_reverse_french_urls_or_numbers():
    text='élève https://example.org/a-b 123'
    characters=['']+list(dict.fromkeys(text))
    ids=[]
    for char in text:ids.extend([characters.index(char),0])
    matrix=np.eye(len(characters),dtype=np.float32)[ids]
    assert arabic_ocr.decode_ctc(matrix,characters)[0]==text


def test_partial_install_never_downloads(tmp_path,monkeypatch):
    monkeypatch.setattr(arabic_ocr,'model_root',lambda:tmp_path)
    (tmp_path/'arabic-print').mkdir()
    (tmp_path/'arabic-print/ready.json').write_text('{}')
    assert not arabic_ocr.available()
    with pytest.raises(RuntimeError,match='complete offline'):
        arabic_ocr.Reader(1)


def test_tesseract_partial_language_success_is_rejected(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from yuzufile import engines
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:False)
    monkeypatch.setattr('yuzufile.neural_text.available',lambda:False)
    monkeypatch.setattr(engines,'tesseract_executable',lambda:'tesseract')
    monkeypatch.setattr(engines,'tesseract_environment',lambda:{})
    image=tmp_path/'page.png'
    image.with_suffix('.pdf').write_bytes(b'partial English output')
    monkeypatch.setattr(engines.subprocess,'run',lambda *a,**k:SimpleNamespace(
        returncode=0,stderr=b"Failed loading language 'ara'"))
    with pytest.raises(engines.ConversionError,match='No partial-language output'):
        engines.recognize_page(image,300,['ara','eng'],1)


def test_independent_detection_recovers_missing_line_and_updates_layout_text(tmp_path):
    from PIL import Image
    from types import SimpleNamespace
    path=tmp_path/'mixed.png';Image.new('RGB',(400,200),'white').save(path)
    reader=arabic_ocr.Reader.__new__(arabic_ocr.Reader)
    box=np.array([[20,30],[370,30],[370,90],[20,90]],dtype=np.float32)
    reader.detector=lambda *a,**k:SimpleNamespace(boxes=[box])
    text='شروط الصلاة وأركانها وواجباتها'
    reader.read_line=lambda *a:(text,.95)
    original=dict(engine='Indra',rotation=0,rows=[],blocks=[
        dict(label='Text',bbox=[0,0,400,100],text='Incorrect earlier transcript')])
    result=reader.refine(path,original)
    assert result['rows'][0]['text']==text
    assert result['blocks'][0]['text']==text
    assert text in result['markdown']
    assert 'Incorrect' not in result['markdown']
