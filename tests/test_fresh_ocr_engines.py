"""Fresh visual recognition must never inherit the input PDF's hidden words."""
import json
from contextlib import contextmanager
from pathlib import Path
import pymupdf
import pytest
from PIL import Image
from yuzufile import engines
from yuzufile.performance import performance_profile
from yuzufile.ocr_clean import DiskBackedDocument


def source_document(count=3):
    document=pymupdf.open()
    for index in range(count):
        page=document.new_page(width=240,height=180)
        page.insert_text((20,45),f'VISIBLE PAGE {index+1}',fontsize=17)
        page.insert_text((20,80),f'POISON_OLD_OCR_{index+1}',render_mode=3)
        document.xref_set_key(page.xref,'PDFaiOCR','true')
    return document


def disable_models(monkeypatch):
    monkeypatch.setattr('yuzufile.neural_text.available',lambda:False)
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:False)


def fake_json_recognizer(events):
    def recognize(image,dpi,languages,number):
        assert len(list(image.parent.glob('page-*.png')))==1
        events.append(('ocr',number))
        with Image.open(image) as raster:
            assert min(raster.convert('L').getextrema())<100
            width,height=raster.size
        result=image.with_suffix('.ocr.json')
        result.write_text(json.dumps(dict(width=width,height=height,rows=[dict(
            text=f'FRESH PAGE {number}',box=[20,35,200,65],score=.99)])))
        return result
    return recognize


def test_clean_then_recognize_is_serial_and_does_not_reuse_old_hidden_text(tmp_path,monkeypatch):
    disable_models(monkeypatch);events=[]
    from yuzufile import ocr_clean
    original=ocr_clean.clean_page
    def clean(page,target):
        events.append(('clean',page.number+1))
        # Preceding page's raster and overlay are gone before preparing another.
        assert not list(tmp_path.glob('page-*'))
        result=original(page,target)
        assert not target[-1].get_text() and not target[-1].get_fonts()
        return result
    monkeypatch.setattr(ocr_clean,'clean_page',clean)
    monkeypatch.setattr(engines,'recognize_page',fake_json_recognizer(events))
    with source_document(3) as source,pymupdf.open() as target:
        source_bytes=source.tobytes(no_new_id=True)
        stats=engines.add_searchable_text(source,tmp_path,['eng'],lambda *a,**k:None,
            performance_profile('high'),force_ocr=True,sequential=True,target_document=target)
        assert events==[(kind,n) for n in range(1,4) for kind in ('clean','ocr')]
        assert stats['ocr_pages']==3 and stats['reused_pages']==0 and stats['page_workers']==1
        assert stats['ocr_parts']==3 and stats['fresh_ocr_pages']==[1,2,3]
        assert stats['fresh_ocr'] and stats['sequential_ocr']
        for index,page in enumerate(target):
            assert f'FRESH PAGE {index+1}' in page.get_text()
            assert 'POISON' not in page.get_text() and 'VISIBLE PAGE' not in page.get_text()
            assert target.xref_get_key(page.xref,'PDFaiFreshOCR')[1]=='true'
            assert target.xref_get_key(page.xref,'PDFaiImageOnly')[1]=='false'
            cache=json.loads((tmp_path/f'fresh-ocr-page-{index+1}.json').read_text())
            assert cache['logical_ocr'] and cache['fresh_ocr']
            assert cache['rows'][0]['text']==f'FRESH PAGE {index+1}'
        assert all('POISON' in page.get_text() for page in source)
        assert source.tobytes(no_new_id=True)==source_bytes
    assert not list(tmp_path.glob('page-*'))


def test_disk_backed_target_can_checkpoint_without_retaining_stale_pages(tmp_path,monkeypatch):
    disable_models(monkeypatch);events=[]
    monkeypatch.setattr(engines,'recognize_page',fake_json_recognizer(events))
    holder=DiskBackedDocument(tmp_path,limit_bytes=1)
    try:
        with source_document(3) as source:
            stats=engines.add_searchable_text(source,tmp_path,['eng'],lambda *a,**k:None,
                performance_profile('high'),target_document=holder)
        assert holder.checkpoints>=2 and stats['recognized_pages']==3
        assert [page.get_text().strip() for page in holder]==[f'FRESH PAGE {n}' for n in range(1,4)]
    finally:holder.close()


def test_page_callback_can_interleave_clean_ocr_and_export_without_resetting_output(tmp_path,monkeypatch):
    disable_models(monkeypatch);events=[]
    monkeypatch.setattr(engines,'recognize_page',fake_json_recognizer(events))
    with source_document(3) as source,pymupdf.open() as target:
        reports=[]
        for index in range(3):
            report=engines.add_searchable_text(source,tmp_path,['eng'],lambda *a,**k:None,
                performance_profile('high'),force_ocr=True,sequential=True,target_document=target,page_numbers=[index])
            reports.append(report)
            events.append(('export',index+1))
            assert len(target)==index+1
            assert target[index].get_text().strip()==f'FRESH PAGE {index+1}'
            assert report['ocr_pages']==1 and report['reused_pages']==0 and report['fresh_ocr_pages']==[index+1]
        assert events==[(kind,n) for n in range(1,4) for kind in ('ocr','export')]
        assert sum(report['recognized_pages'] for report in reports)==3
        assert len(list(tmp_path.glob('fresh-ocr-page-*.json')))==3
        with pytest.raises(engines.ConversionError,match='append in order'):
            engines.add_searchable_text(source,tmp_path,['eng'],lambda *a,**k:None,target_document=target,page_numbers=[0])


@pytest.mark.parametrize('pages',[[1],[0,2],[1,0],[0,0],[-1],[True],[20]])
def test_partial_fresh_ocr_rejects_gaps_duplicates_and_invalid_indices(tmp_path,monkeypatch,pages):
    with source_document(3) as source,pymupdf.open() as target:
        with pytest.raises(engines.ConversionError):
            engines.add_searchable_text(source,tmp_path,['eng'],lambda *a,**k:None,target_document=target,page_numbers=pages)


def test_tesseract_cache_comes_from_only_the_fresh_result_overlay(tmp_path,monkeypatch):
    disable_models(monkeypatch)
    def recognize(image,*args):
        result=image.with_suffix('.pdf')
        with pymupdf.open() as overlay:
            overlay.new_page(width=240,height=180).insert_text((20,55),'FRESH TESSERACT TEXT',render_mode=3)
            overlay.save(result)
        return result
    monkeypatch.setattr(engines,'recognize_page',recognize)
    with source_document(1) as source,pymupdf.open() as target:
        engines.add_searchable_text(source,tmp_path,['eng'],lambda *a,**k:None,target_document=target)
        assert target[0].get_text().strip()=='FRESH TESSERACT TEXT'
        assert target.xref_get_key(target[0].xref,'PDFaiFreshOCR')[1]=='true'
    cache=json.loads((tmp_path/'fresh-ocr-page-1.json').read_text())
    assert cache['engine']=='Tesseract 5' and cache['rows'][0]['text']=='FRESH TESSERACT TEXT'
    assert 'POISON' not in json.dumps(cache)


@pytest.mark.parametrize('rotation,box,size',[
    (0,[10,20,30,40],(100,200)),(90,[160,10,180,30],(200,100)),
    (180,[70,160,90,180],(100,200)),(270,[20,70,40,90],(200,100))])
def test_generic_cache_normalizes_upright_coordinates_without_changing_indra_data(rotation,box,size):
    data=dict(width=100,height=200,rotation=rotation,engine='Indra OCR',
        rows=[dict(box=[10,20,30,40],text='مرحبا',score=.98)],blocks=[dict(label='Picture',bbox=[10,20,30,40])])
    cached=engines._fresh_cache_data(data)
    assert cached['rows'][0]['box']==box and cached['blocks'][0]['bbox']==box
    assert (cached['width'],cached['height'])==size and cached['rotation']==0
    assert cached['source_rotation']==rotation and cached['rows'][0]['text']=='مرحبا'
    assert data['rotation']==rotation and data['rows'][0]['box']==[10,20,30,40]


def test_empty_recognition_still_marks_page_fresh_and_never_reuses_old_words(tmp_path,monkeypatch):
    disable_models(monkeypatch)
    def empty(image,*args):
        result=image.with_suffix('.ocr.json');result.write_text(json.dumps(dict(width=100,height=100,rows=[])))
        return result
    monkeypatch.setattr(engines,'recognize_page',empty)
    with source_document(1) as source,pymupdf.open() as target:
        stats=engines.add_searchable_text(source,tmp_path,['eng'],lambda *a,**k:None,target_document=target)
        assert stats['empty_pages']==[1] and stats['reused_pages']==0
        assert not target[0].get_text() and target.xref_get_key(target[0].xref,'PDFaiFreshOCR')[1]=='true'
        assert target.xref_get_key(target[0].xref,'PDFaiImageOnly')[1]=='true'


def test_notify_cancellation_between_pages_never_queues_the_next_raster(tmp_path,monkeypatch):
    disable_models(monkeypatch);events=[]
    monkeypatch.setattr(engines,'recognize_page',fake_json_recognizer(events))
    def notify(stage,**extra):
        if stage.startswith('Cleaning old text') and extra['page']==2:raise RuntimeError('cancelled')
    with source_document(3) as source,pymupdf.open() as target:
        with pytest.raises(RuntimeError,match='cancelled'):
            engines.add_searchable_text(source,tmp_path,['eng'],notify,target_document=target)
        assert len(target)==1 and events==[('ocr',1)]
    assert not list(tmp_path.glob('page-*'))


def test_fresh_modes_reject_unsafe_existing_text_instead_of_silently_reusing_it(tmp_path):
    with source_document(1) as source:
        with pytest.raises(engines.ConversionError,match='separate image-only'):
            engines.add_searchable_text(source,tmp_path,['eng'],lambda *a,**k:None,force_ocr=True)
        with pytest.raises(engines.ConversionError,match='freshly recognized'):
            engines.write_markdown(source,tmp_path/'out.md',lambda *a,**k:None,fresh_ocr=True)


def test_fresh_markdown_reuses_indra_result_without_recognizing_old_pdf_again(tmp_path,monkeypatch):
    from yuzufile import indra_engine
    scratch=tmp_path/'scratch';scratch.mkdir()
    data=dict(width=240,height=180,rotation=0,engine=indra_engine.ENGINE,
        markdown='# Fresh heading',rows=[dict(text='Fresh heading',score=.99,box=[20,30,180,55])],blocks=[])
    (scratch/'indra-page-1.json').write_text(json.dumps(data))
    monkeypatch.setattr(indra_engine,'available',lambda:True)
    monkeypatch.setattr(indra_engine,'recognize',lambda *a:pytest.fail('The first OCR result must be reused'))
    monkeypatch.setattr('yuzufile.vision_runtime.available',lambda:False)
    with pymupdf.open() as fresh:
        page=fresh.new_page(width=240,height=180);page.insert_text((20,55),'Fresh heading',render_mode=3)
        fresh.xref_set_key(page.xref,'PDFaiFreshOCR','true')
        fresh.xref_set_key(page.xref,'PDFaiOCR','true')
        engines.write_markdown(fresh,tmp_path/'out.md',lambda *a,**k:None,languages=['eng'],fresh_ocr=True)
    assert (tmp_path/'out.md').read_text().strip()=='# Fresh heading'


def test_fresh_markdown_uses_serial_visual_parts_without_lowering_model_thread_budget(tmp_path,monkeypatch):
    monkeypatch.setattr('yuzufile.indra_engine.available',lambda:False)
    monkeypatch.setattr('yuzufile.vision_runtime.available',lambda:True)
    calls=[]
    def write(document,destination,notify,performance,languages,**options):
        calls.append((options,performance.workers,languages));destination.write_text('Fresh visual Markdown');return []
    monkeypatch.setattr('yuzufile.neural_markdown.write',write)
    with pymupdf.open() as fresh:
        page=fresh.new_page();fresh.xref_set_key(page.xref,'PDFaiFreshOCR','true')
        engines.write_markdown(fresh,tmp_path/'out.md',lambda *a,**k:None,performance_profile('high'),['ara'],fresh_ocr=True)
    assert calls==[({'sequential':True},4,['ara'])]


def test_indra_table_fallback_keeps_fresh_provenance_on_its_one_page_copy(tmp_path,monkeypatch):
    from yuzufile import indra_engine
    scratch=tmp_path/'scratch';scratch.mkdir()
    data=dict(width=240,height=180,rotation=0,engine=indra_engine.ENGINE,
        markdown='<table>Needs verification</table>',rows=[],blocks=[dict(label='Table')])
    (scratch/'indra-page-1.json').write_text(json.dumps(data))
    monkeypatch.setattr('yuzufile.vision_runtime.available',lambda:True)
    calls=[]
    def detailed(document,destination,*args,**options):
        assert len(document)==1 and document.xref_get_key(document[0].xref,'PDFaiFreshOCR')[1]=='true'
        assert options['sequential'] is True
        calls.append(1);destination.write_text('Fresh verified table');return []
    monkeypatch.setattr('yuzufile.neural_markdown.write',detailed)
    with pymupdf.open() as fresh:
        page=fresh.new_page();fresh.xref_set_key(page.xref,'PDFaiFreshOCR','true')
        indra_engine.write_markdown(fresh,tmp_path/'out.md',lambda *a,**k:None,performance_profile('high'),['eng'],fresh_ocr=True)
    assert calls==[1] and (tmp_path/'out.md').read_text().strip()=='Fresh verified table'


def test_neural_markdown_releases_each_page_before_starting_the_next(tmp_path,monkeypatch):
    from yuzufile import neural_markdown,neural_task
    (tmp_path/'scratch').mkdir();calls=[]
    @contextmanager
    def unavailable(*args):yield None
    monkeypatch.setattr(neural_markdown,'optional_runtime',unavailable)
    def run(kind,images,languages,threads):
        calls.append((kind,list(images),threads))
        assert len(images)==1
        if kind=='rapid':return [[dict(text='Fresh text',score=.99,box=[20,20,180,55])]]
        return [[]]
    monkeypatch.setattr(neural_task,'run',run)
    with pymupdf.open() as fresh:
        for _ in range(3):fresh.new_page(width=240,height=180)
        neural_markdown.write(fresh,tmp_path/'out.md',lambda *a,**k:None,performance_profile('high'),['eng'],sequential=True)
    assert len([call for call in calls if call[0]=='rapid'])==3
    assert not list((tmp_path/'scratch').glob('*.png'))
    assert (tmp_path/'out.md').read_text().count('Fresh text')==3


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_fresh_figure_hints_use_visible_rotation_and_crop_only_clean_page_pixels(tmp_path,monkeypatch,rotation):
    disable_models(monkeypatch);scratch=tmp_path/'scratch';scratch.mkdir()
    events=[];monkeypatch.setattr(engines,'recognize_page',fake_json_recognizer(events))
    with source_document(1) as source,pymupdf.open() as target:
        image=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,80,60),False)
        image.set_rect(image.irect,(0,220,70))
        source[0].insert_image(pymupdf.Rect(25,100,145,170),pixmap=image)
        source[0].set_rotation(rotation)
        expected=(pymupdf.Rect(source[0].get_image_info()[0]['bbox'])*source[0].rotation_matrix)&source[0].rect
        engines.add_searchable_text(source,scratch,['eng'],lambda *a,**k:None,target_document=target)
        cache=json.loads((scratch/'fresh-ocr-page-1.json').read_text())
        assert cache['source_figures'][0]==pytest.approx(tuple(expected),abs=.001)
        assert 'POISON' not in json.dumps(cache)
        markdown=engines._fresh_figure_markdown(target[0],1,tmp_path/'out.md','Fresh text')
        assert 'assets/fresh-figure-1-0.png' in markdown
    with Image.open(tmp_path/'assets/fresh-figure-1-0.png') as exported:
        red,green,blue=exported.getpixel((exported.width//2,exported.height//2))
        assert red<20 and green>180 and blue<110
        assert (exported.width>exported.height)==(rotation%180==0)


def test_source_figure_hints_exclude_full_scans_mask_images_and_duplicate_placements():
    class Source:
        rect=pymupdf.Rect(0,0,400,400)
        rotation_matrix=pymupdf.Matrix(1,1)
        def get_images(self,full=False):return [(10,11)]
        def get_image_info(self,xrefs=False):return [
            dict(xref=11,bbox=[20,20,120,90]),dict(xref=20,bbox=[0,0,400,400]),
            dict(xref=30,bbox=[40,160,180,260]),dict(xref=31,bbox=[40,160,180,260])]
    assert engines._source_figure_boxes(Source())==[[40.,160.,180.,260.]]


def test_fresh_figure_fallback_does_not_duplicate_model_asset_or_export_text_panels(tmp_path):
    scratch=tmp_path/'scratch';scratch.mkdir();assets=tmp_path/'assets';assets.mkdir()
    cache=scratch/'fresh-ocr-page-1.json'
    data=dict(width=240,height=180,fresh_ocr=True,rows=[],
        source_figures=[[20,50,140,120]],blocks=[dict(label='Picture',bbox=[20,50,140,120])])
    cache.write_text(json.dumps(data));(assets/'indra-1-0.png').write_bytes(b'existing model image')
    with pymupdf.open() as target:
        page=target.new_page(width=240,height=180)
        page.draw_rect(pymupdf.Rect(20,50,140,120),color=None,fill=(0,.8,.3))
        text='Fresh text\n![](assets/indra-1-0.png)'
        assert engines._fresh_figure_markdown(page,1,tmp_path/'out.md',text)==text
        assert not list(assets.glob('fresh-figure-*'))
        data['blocks']=[];data['rows']=[dict(box=[20,y,140,y+22],text='Fresh row') for y in (50,73,96)]
        cache.write_text(json.dumps(data))
        assert engines._fresh_figure_markdown(page,1,tmp_path/'out.md','Fresh rows')=='Fresh rows'
        assert not list(assets.glob('fresh-figure-*'))
