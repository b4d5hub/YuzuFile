import hashlib
import json

import pymupdf
import pytest

from yuzufile.cleanup import clean_document,estimate_angle,settings,transform_page
from yuzufile.performance import performance_profile
from yuzufile.worker import convert
from artifact_helpers import artifact_path


def text_page(doc):
    p=doc.new_page(width=600,height=800)
    for i in range(8):
        p.insert_text((110,160+i*30),f'Read comfortably. Important content {i+1}: 43% and 57%.',fontsize=12)
    p.insert_text((260,720),'Page 1',fontsize=10)
    return p


def skewed(scan=False):
    original=pymupdf.open()
    text_page(original)
    rotated=pymupdf.open()
    page=rotated.new_page(width=642,height=832)
    page.show_pdf_page(page.rect,original,rotate=-3)
    original.close()
    if not scan:return rotated
    result=pymupdf.open()
    page=result.new_page(width=642,height=832)
    page.insert_image(page.rect,pixmap=rotated[0].get_pixmap(dpi=150))
    rotated.close()
    return result


@pytest.mark.parametrize('scan',[False,True])
def test_deskew_finds_correct_angle_without_rasterizing_export(scan):
    with skewed(scan) as doc:
        angle,method=estimate_angle(doc[0])
        assert abs(angle-3)<.35,(angle,method)
        output,details,_=transform_page(doc,0,settings({'trim':False}))
        try:
            assert abs(details['angle_degrees']-3)<.35
            if not scan:
                assert 'Important content' in output[0].get_text()
                assert abs(estimate_angle(output[0])[0])<.2
            else:
                # Source raster is retained; rotation uses PDF geometry.
                old=doc.extract_image(doc[0].get_images()[0][0])['image']
                new=output.extract_image(output[0].get_images()[0][0])['image']
                assert old==new
        finally:output.close()


def test_trim_preserves_footer_and_native_text():
    with pymupdf.open() as doc:
        text_page(doc)
        output,details,_=transform_page(doc,0,settings({'straighten':False}))
        try:
            assert details['trimmed']
            assert output[0].rect.width<doc[0].rect.width
            assert output[0].rect.height>550
            assert 'Page 1' in output[0].get_text()
            assert 'Important content 8' in output[0].get_text()
        finally:output.close()


def test_trim_keeps_faint_vector_artwork():
    with pymupdf.open() as doc:
        text_page(doc)
        doc[0].draw_rect(pymupdf.Rect(500,680,550,740),fill=(.99,.99,.99),color=None)
        output,detail,_=transform_page(doc,0,settings({'straighten':False}))
        try:
            assert output[0].rect.width > 450
            assert any(drawing['fill']==pytest.approx((.99,.99,.99)) for drawing in output[0].get_drawings())
        finally:output.close()


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_rotated_crop_boxes_keep_visible_text(rotation):
    with pymupdf.open() as doc:
        p=text_page(doc)
        p.set_cropbox(pymupdf.Rect(30,40,570,780))
        p.set_rotation(rotation)
        output,details,_=transform_page(doc,0,settings({'straighten':False}))
        try:
            assert 'Page 1' in output[0].get_text()
            assert 'Important content 1' in output[0].get_text()
            assert output[0].rect.width <= p.rect.width
            assert output[0].rect.height <= p.rect.height
        finally:output.close()


def test_blank_page_is_not_cropped_or_rotated():
    with pymupdf.open() as doc:
        doc.new_page()
        output,details,_=transform_page(doc,0,settings())
        try:
            assert not details['changed']
            assert details['warnings']
        finally:output.close()


def test_existing_ocr_marker_survives_straightening():
    from yuzufile.engines import page_needs_ocr
    with skewed() as doc:
        doc.xref_set_key(doc[0].xref,'PDFaiOCR','true')
        output,details,_=transform_page(doc,0,settings())
        try:
            assert details['angle_degrees']
            assert output.xref_get_key(output[0].xref,'PDFaiOCR')[1]=='true'
            assert not page_needs_ocr(output[0])
        finally:output.close()


def test_links_bookmarks_attachments_and_ranges_survive(tmp_path):
    with pymupdf.open() as doc:
        text_page(doc)
        text_page(doc)
        doc[0].insert_link({'kind':pymupdf.LINK_URI,'from':pymupdf.Rect(110,150,220,165),'uri':'https://example.com'})
        doc[1].insert_link({'kind':pymupdf.LINK_GOTO,'from':pymupdf.Rect(110,150,220,165),'page':0,'to':pymupdf.Point(110,160)})
        doc.set_toc([[1,'First chapter',1],[1,'Second chapter',2]])
        doc.embfile_add('notes.txt',b'Keep this attachment')
        scratch=tmp_path/'scratch'
        scratch.mkdir()
        output,details,warnings=clean_document(doc,{'pages':'1','straighten':False},scratch)
        try:
            assert len(output)==2 and details['trimmed_pages']==1
            assert output[1].rect==doc[1].rect
            assert output.embfile_get('notes.txt')==b'Keep this attachment'
            assert output.get_toc()==doc.get_toc()
            saved=tmp_path/'cleaned.pdf'
            output.save(saved,garbage=3,deflate=True)
        finally:output.close()
    with pymupdf.open(saved) as result:
        assert result[0].get_links()[0]['uri']=='https://example.com'
        assert result[1].get_links()[0]['page']==0
        assert result[1].get_links()[0]['to'].x<20
        assert not warnings


def test_deskew_link_coordinates_follow_transformed_text(tmp_path):
    with skewed() as doc:
        first=doc[0].get_text('words')[0]
        doc[0].insert_link({'kind':pymupdf.LINK_URI,'from':pymupdf.Rect(first[:4]),'uri':'https://example.com'})
        scratch=tmp_path/'scratch'
        scratch.mkdir()
        output,_,_=clean_document(doc,settings(),scratch)
        try:
            word=pymupdf.Rect(output[0].get_text('words')[0][:4])
            link=output[0].get_links()[0]['from']
            assert abs((word.x0+word.x1-link.x0-link.x1)/2)<2
            assert abs((word.y0+word.y1-link.y0-link.y1)/2)<2
        finally:output.close()


def test_annotations_prevent_arbitrary_rotation_and_are_retained():
    with skewed() as doc:
        doc[0].add_text_annot((120,120),'Important annotation')
        output,details,_=transform_page(doc,0,settings())
        try:
            assert details['angle_degrees']==0
            assert any('annotations' in w for w in details['warnings'])
            assert next(output[0].annots()).info['content']=='Important annotation'
        finally:output.close()


@pytest.mark.parametrize('value',[{'straighten':False,'trim':False},{'padding_mm':0},{'padding_mm':float('nan')},{'pages':'9-2'}])
def test_invalid_options_are_rejected(value):
    with pytest.raises(ValueError):settings(value)


def test_worker_cleanup_without_ocr_preserves_source(digital_pdf,tmp_path):
    before=hashlib.sha256(digital_pdf.read_bytes()).digest()
    root=tmp_path/'job'
    convert({'source':str(digital_pdf),'root':str(root),'mode':'cleanup','languages':[],
             'cleanup_settings':{'straighten':False,'padding_mm':4}})
    with pymupdf.open(artifact_path(root,'pdf')) as doc:
        assert 'Hello world.' in doc[0].get_text()
        assert doc[0].rect.height<250
    metadata=json.loads((root/'result/manifest.json').read_text())['metadata']
    assert metadata['cleanup']['trimmed_pages']==1
    assert metadata['ocr_pages']==0
    assert hashlib.sha256(digital_pdf.read_bytes()).digest()==before


def test_compression_fallback_uses_cleaned_pages(digital_pdf,tmp_path,monkeypatch):
    import shutil
    def no_savings(document,source,target,*args):
        with pymupdf.open(source) as doc:assert doc[0].rect.height<250
        shutil.copyfile(source,target)
        return {'input_bytes':source.stat().st_size,'output_bytes':target.stat().st_size,'warnings':[]}
    monkeypatch.setattr('yuzufile.compression.compress_pdf',no_savings)
    convert({'source':str(digital_pdf),'root':str(tmp_path/'job'),'mode':'compress_cleanup','languages':[],
             'cleanup_settings':{'straighten':False}})


def test_selected_forms_fail_safely_but_unselected_forms_survive(tmp_path):
    with pymupdf.open() as doc:
        text_page(doc)
        p=text_page(doc)
        widget=pymupdf.Widget()
        widget.field_name='Name'
        widget.field_type=pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.field_value='Keep this field'
        widget.rect=pymupdf.Rect(50,50,250,85)
        p.add_widget(widget)
        with pytest.raises(ValueError,match='form fields'):
            transform_page(doc,1,settings())
        scratch=tmp_path/'scratch'
        scratch.mkdir()
        result,_,_=clean_document(doc,{'pages':'1','straighten':False},scratch)
        try:
            assert next(result[1].widgets()).field_value=='Keep this field'
        finally:result.close()


def test_stored_cleanup_settings_and_schema_defaults(store,digital_pdf):
    config={'straighten':False,'trim':True,'padding_mm':5,'pages':'1'}
    job=store.create(digital_pdf,'cleanup',[],cleanup_settings=config)
    assert json.loads(store.get(job)['cleanup_settings'])==settings(config)
    legacy=store.create(digital_pdf,'pdf',['eng'])
    assert json.loads(store.get(legacy)['cleanup_settings'])=={}
    assert store.db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]==7
