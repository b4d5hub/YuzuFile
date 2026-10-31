"""Real cleanup fixtures and preserved-content checks; run from project root."""
from pathlib import Path
import hashlib
import json
import sys

import pymupdf
from yuzufile.cleanup import estimate_angle
from yuzufile.worker import convert


def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else 'tmp/cleanup-qa').resolve()
    root.mkdir(parents=True,exist_ok=True)
    native,scan=root/'native.pdf',root/'scanned.pdf'
    with pymupdf.open() as upright,pymupdf.open() as original:
        p=upright.new_page(width=600,height=800)
        p.insert_text((100,140),'Read comfortably',fontsize=24)
        for i in range(8):
            p.insert_text((100,185+i*28),f'Important content {i+1}: 43% and 57%. Keep every word.',fontsize=12)
        p.draw_rect(pymupdf.Rect(100,450,260,540),color=(.1,.3,.5),fill=(.85,.92,1))
        p.draw_circle((180,495),25,color=(.1,.3,.5),fill=(.1,.3,.5))
        p.insert_text((270,720),'Page 1',fontsize=10)
        p=original.new_page(width=642,height=832)
        p.show_pdf_page(p.rect,upright,rotate=-3)
        original.set_toc([[1,'Reading sample',1]])
        original.save(native)
        with pymupdf.open() as raster:
            p=raster.new_page(width=642,height=832)
            p.insert_image(p.rect,pixmap=original[0].get_pixmap(dpi=180))
            raster.save(scan)
    results=[]
    for name,source in (('native',native),('scanned',scan)):
        before=hashlib.sha256(source.read_bytes()).hexdigest()
        job=root/(name+'-job')
        convert({'source':str(source),'root':str(job),'mode':'cleanup','languages':[],
                 'performance':'low','cleanup_settings':{'padding_mm':3}})
        result=job/'result/document.cleaned.pdf'
        with pymupdf.open(source) as old,pymupdf.open(result) as cleaned:
            assert len(cleaned)==len(old)
            angle,method=estimate_angle(cleaned[0])
            assert abs(angle)<.25,(name,angle,method)
            assert cleaned[0].rect.width<old[0].rect.width
            assert cleaned[0].rect.height<old[0].rect.height
            if name=='native':
                assert 'Important content 8' in cleaned[0].get_text()
                assert 'Page 1' in cleaned[0].get_text()
                assert cleaned.get_toc()==old.get_toc()
            else:
                old_image=old.extract_image(old[0].get_images()[0][0])['image']
                new_image=cleaned.extract_image(cleaned[0].get_images()[0][0])['image']
                assert old_image==new_image
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        results.append({'case':name,'remaining_angle':angle,'result':str(result)})
    (root/'verification.json').write_text(json.dumps(results,indent=2))
    print(json.dumps({'checks':'passed','results':results}))


if __name__=='__main__':main()
