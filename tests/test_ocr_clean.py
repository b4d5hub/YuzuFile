import hashlib,json
from pathlib import Path
import pymupdf,pytest
from yuzufile.ocr_clean import DiskBackedDocument,clean_page,image_only_document,validate_image_only
from yuzufile.worker import convert


@pytest.fixture
def layered_pdf(tmp_path):
    path=tmp_path/'Already OCR.pdf'
    with pymupdf.open() as document:
        for number in range(3):
            page=document.new_page(width=400,height=560)
            page.insert_text((40,80),f'VISIBLE PAGE {number+1}',fontsize=26)
            page.insert_text((40,120),'This is the page that must remain visible.',fontsize=12)
            page.insert_text((30,180),'STALE WRONG OCR DO NOT REUSE',render_mode=3)
            page.draw_rect(pymupdf.Rect(40,230,280,350),color=(.1,.3,.6),fill=(.8,.9,1))
            page.insert_link({'kind':pymupdf.LINK_URI,'uri':'https://example.org','from':pymupdf.Rect(40,100,270,135)})
            if number==1:page.set_rotation(90)
        document.set_toc([[1,'First page',1],[1,'Second page',2]])
        document.save(path)
    return path


def test_image_only_preserves_visible_pages_and_removes_all_text(layered_pdf,tmp_path):
    digest=hashlib.sha256(layered_pdf.read_bytes()).hexdigest()
    scratch=tmp_path/'scratch';scratch.mkdir()
    with pymupdf.open(layered_pdf) as source:
        cleaned,details,warnings=image_only_document(source,scratch)
        with cleaned:
            validate_image_only(cleaned);assert len(cleaned)==3
            assert details['pages_with_old_text']==3 and details['page_workers']==1
            assert cleaned.get_toc()==source.get_toc()
            assert details['max_pixels']<=8_000_000
            for index in range(3):
                assert cleaned[index].rect==source[index].rect
                assert not cleaned[index].get_text() and not cleaned[index].get_fonts()
                assert len(cleaned[index].get_images())==1
                assert cleaned[index].get_links()[0]['uri']=='https://example.org'
                # Re-render the written page at reading resolution: clean output
                # must preserve colored graphics and visible text, not white them out.
                original=source[index].get_pixmap(matrix=pymupdf.Matrix(1,1),colorspace=pymupdf.csRGB,alpha=False)
                result=cleaned[index].get_pixmap(matrix=pymupdf.Matrix(1,1),colorspace=pymupdf.csRGB,alpha=False)
                assert (original.width,original.height)==(result.width,result.height)
                from PIL import Image,ImageChops,ImageStat
                a=Image.frombytes('RGB',(original.width,original.height),original.samples)
                b=Image.frombytes('RGB',(result.width,result.height),result.samples)
                assert max(ImageStat.Stat(ImageChops.difference(a,b)).mean)<3
            output=tmp_path/'Image only.pdf';cleaned.save(output,garbage=4,deflate=True)
    with pymupdf.open(output) as written:validate_image_only(written)
    assert hashlib.sha256(layered_pdf.read_bytes()).hexdigest()==digest


def test_checkpoint_reopens_pages_without_losing_fresh_text(layered_pdf,tmp_path):
    holder=DiskBackedDocument(tmp_path,limit_bytes=1)
    with pymupdf.open(layered_pdf) as source:
        for index in range(3):
            clean_page(source[index],holder)
            holder[index].insert_text((30,35),f'FRESH RESULT {index+1}')
        output=holder.detach()
    with output:
        assert holder.checkpoints>=3
        assert [p.get_text().strip() for p in output]==['FRESH RESULT 1','FRESH RESULT 2','FRESH RESULT 3']
        assert all('STALE' not in p.get_text() for p in output)
    holder.close()


@pytest.mark.parametrize('mode',['remove_ocr','remove_ocr_compress'])
def test_worker_image_only_jobs_have_one_nonsearchable_pdf_and_no_ocr(layered_pdf,tmp_path,monkeypatch,mode):
    monkeypatch.setattr('yuzufile.worker.add_searchable_text',lambda *a,**kw:pytest.fail('Remove OCR must not run recognition'))
    root=tmp_path/mode
    convert(dict(root=str(root),source=str(layered_pdf),mode=mode,languages=[],compression='lossless',performance='low'))
    manifest=json.loads((root/'result/manifest.json').read_text())
    pdfs=[a for a in manifest['artifacts'] if a['kind']=='pdf'];assert len(pdfs)==1
    with pymupdf.open(root/pdfs[0]['path']) as document:
        validate_image_only(document);assert len(document)==3
        assert document.get_toc()[1][1]=='Second page'
    assert manifest['metadata']['remove_ocr']['image_only']
    assert manifest['metadata']['text_preparation']['old_text_reused'] is False
    assert not any('searchable text' in warning for warning in manifest['metadata']['warnings'])
    assert not (root/'staging').exists()
