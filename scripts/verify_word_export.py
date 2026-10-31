"""Reproducible native/scanned Word fixture; run from the project root."""
from pathlib import Path
import json
import sys
import pymupdf

from yuzufile.worker import convert


def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else 'tmp/word-real-qa').resolve()
    root.mkdir(parents=True,exist_ok=True)
    native=root/'native.pdf'
    scanned=root/'scanned.pdf'
    with pymupdf.open() as pdf:
        p=pdf.new_page()
        p.insert_text((50,70),'Quarterly results',fontsize=22)
        p.insert_text((50,100),'Editable text, tables and replaceable figures.',fontsize=12)
        for x in (50,220,390):
            p.draw_line((x,140),(x,260))
        for y in (140,180,220,260):
            p.draw_line((50,y),(390,y))
        for r,row in enumerate((('Category','Share'),('SMB','43%'),('Enterprise','57%'))):
            for c,text in enumerate(row):
                p.insert_text((60+c*170,165+r*40),text,fontsize=12)
        p.draw_rect(pymupdf.Rect(50,300,200,390),color=(.1,.3,.5),fill=(.8,.9,1))
        p.draw_circle((125,345),25,color=(.1,.3,.5),fill=(.1,.3,.5))
        p.insert_text((50,430),'Revenue: 12,345.67 EUR. Total: 100%.',fontsize=12)
        pdf.save(native)
        with pymupdf.open() as scan:
            page=scan.new_page(width=p.rect.width,height=p.rect.height)
            page.insert_image(page.rect,pixmap=p.get_pixmap(dpi=200))
            scan.save(scanned)
    for name,source in (('native',native),('scanned',scanned)):
        convert({'root':str(root/name),'source':str(source),'mode':'word','languages':['eng'],
                 'performance':'balanced'})
        from docx import Document
        doc=Document(root/name/'result/document.docx')
        editable='\n'.join(p.text for p in doc.paragraphs)+'\n'+'\n'.join(c.text for t in doc.tables for row in t.rows for c in row.cells)
        assert all(token in editable for token in ('43','57','12,345.67')),(name,editable)
        assert doc.tables,(name,'No editable table')
        assert len(doc.inline_shapes)==1,(name,'Expected one figure, without duplicating the table as an image')
    print(json.dumps({'qa_root':str(root),'result':'passed'}))


if __name__=='__main__':
    main()
