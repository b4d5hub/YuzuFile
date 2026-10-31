"""Deterministic content recovery and model lifecycle contracts, without inference."""
from pathlib import Path
import pytest
from yuzufile.neural_markdown import blocks, missing_rows, optional_runtime
from yuzufile import vision_runtime


def test_scan_margin_trim_keeps_faint_footer(tmp_path):
    import pymupdf
    from yuzufile.neural_markdown import prepare
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72,90), 'Main heading', fontsize=22)
        page.insert_text((72,780), 'Faint footer', fontsize=14, color=(.97,.97,.97))
        width, height = prepare(page, page.rect, tmp_path/'faint.png')
    assert height > 1600  # Footer must prevent a heading-only crop.


def test_detail_rerender_keeps_offset_region_after_margin_trim(tmp_path):
    import pymupdf
    from PIL import Image
    from yuzufile.neural_markdown import prepare, render_detail
    with pymupdf.open() as doc:
        page = doc.new_page(width=800,height=600)
        page.draw_rect(pymupdf.Rect(520,380,620,430),fill=(1,0,0),color=None)
        region=pymupdf.Rect(400,300,780,560)
        transform={}
        width,height=prepare(page,region,tmp_path/'region.png',transform)
        item=dict(page=1,transform=transform)
        render_detail(doc,item,(0,0,width,height),tmp_path/'detail.png')
    with Image.open(tmp_path/'detail.png') as result:
        red,green,blue=result.getpixel((result.width//2,result.height//2))
        assert red > 240 and green < 20 and blue < 20


def test_grounded_inline_output_keeps_text_and_coordinates():
    result = blocks('![title](110,81,604,122) # Report\n\n![text](118,154,450,174) Hello world.')
    assert result == [dict(kind='title', box=[.11,.081,.604,.122], text='# Report'),
                      dict(kind='text', box=[.118,.154,.45,.174], text='Hello world.')]


def test_recovery_retains_missing_label_without_repeating_punctuation_variants():
    rows = [dict(text='43% SMB', score=.99),dict(text='57% Enterprise',score=.98),
            dict(text='People → Processes → Technology',score=.95)]
    assert missing_rows(rows, '43 % SMB\nPeople - Processes - Technology') == [rows[1]]


def test_recovery_does_not_accept_changed_numbers_as_a_near_match():
    row=dict(text='Enterprise customers account for 57 percent',score=.99)
    assert missing_rows([row],'Enterprise customers account for 51 percent') == [row]


def test_helper_protocol_preserves_arabic_with_windows_console_encoding(monkeypatch):
    import io,json,sys
    from yuzufile import neural_task
    class Reader:
        def __init__(self,*args):pass
        def read(self,path):return [dict(text='مرحبا بالعالم')]
    output=io.BytesIO()
    console=io.TextIOWrapper(output,encoding='cp1252')
    monkeypatch.setattr('yuzufile.neural_text.RapidReader',Reader)
    monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps(dict(kind='rapid',languages=['ara'],threads=1,images=['sample.png']))))
    monkeypatch.setattr(sys,'stdout',console)
    assert neural_task.main() == 0
    payload=output.getvalue()
    assert payload.isascii()
    assert json.loads(payload)[0][0]['text'] == 'مرحبا بالعالم'


def test_native_pdf_with_tiny_logo_uses_fast_text_path(digital_pdf,tmp_path,monkeypatch):
    import pymupdf
    from yuzufile.engines import write_markdown
    def unexpected(*args,**kwargs):raise AssertionError('A tiny logo must not require visual models')
    monkeypatch.setattr('yuzufile.vision_runtime.available',lambda:True)
    monkeypatch.setattr('yuzufile.neural_markdown.write',unexpected)
    with pymupdf.open(digital_pdf) as doc:
        logo=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,8,8),False)
        logo.clear_with(0)
        doc[0].insert_image(pymupdf.Rect(20,20,28,28),pixmap=logo)
        write_markdown(doc,tmp_path/'native-logo.md',lambda *args,**kwargs:None)
    assert 'Hello world' in (tmp_path/'native-logo.md').read_text(encoding='utf-8')


def test_native_photo_with_no_detected_text_keeps_fast_path_and_assets(digital_pdf,tmp_path,monkeypatch):
    import pymupdf
    from yuzufile.engines import write_markdown
    def unexpected(*args,**kwargs):raise AssertionError('Confirmed text-free photo needs no visual inference')
    monkeypatch.setattr('yuzufile.vision_runtime.available',lambda:True)
    monkeypatch.setattr('yuzufile.neural_markdown.write',unexpected)
    with pymupdf.open(digital_pdf) as doc:
        photo=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,80,50),False)
        photo.clear_with(100)
        doc[0].insert_image(pymupdf.Rect(72,300,250,410),pixmap=photo)
        write_markdown(doc,tmp_path/'native-photo.md',lambda *args,**kwargs:None,native_image_pages=[1])
    text=(tmp_path/'native-photo.md').read_text(encoding='utf-8')
    assert 'Hello world' in text and 'assets/' in text


def test_unavailable_model_releases_process_and_reports_fallback(tmp_path, monkeypatch):
    class Broken:
        def __init__(self,*args): pass
        def __enter__(self): raise RuntimeError('No memory')
    monkeypatch.setattr('yuzufile.neural_markdown.VisionRuntime', Broken)
    warnings, used = [], set()
    with optional_runtime('lighton', tmp_path, 1, warnings, used) as runtime:
        assert runtime is None
    assert used == set()
    assert 'retained other OCR results' in warnings[0]


def test_inference_error_still_closes_loaded_model(tmp_path, monkeypatch):
    events = []
    class Loaded:
        def __init__(self,*args): pass
        def __enter__(self): events.append('load')
        def __exit__(self,*args): events.append('close')
    monkeypatch.setattr('yuzufile.neural_markdown.VisionRuntime', Loaded)
    with pytest.raises(ValueError):
        with optional_runtime('paddle', tmp_path, 1, [], set()):
            raise ValueError('malformed response')
    assert events == ['load','close']
