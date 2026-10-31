"""Bounded detailed recovery for legacy Arabic pages fast OCR cannot read."""
from pathlib import Path
import json
import math
import re

import pymupdf
from PIL import Image
from yuzufile.word_rtl import arabic


def recover(page,primary,scratch,performance,notify):
    from yuzufile import neural_text
    from yuzufile.vision_runtime import VisionRuntime,available
    if not available():raise RuntimeError('Detailed local OCR is unavailable for this legacy font.')
    image=scratch/'legacy-detailed.png';result=None
    try:
        scale=min(360/72,math.sqrt(8_000_000/max(1,page.rect.get_area())))
        pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False,annots=False);pix.save(image);del pix
        result=neural_text.recognize(image,['ara'])
        secondary=json.loads(result.read_text(encoding='utf-8'))
        rows=sorted(secondary['rows'],key=lambda r:r['box'][1])
        if not rows:raise RuntimeError('No text regions could be detected for detailed Arabic OCR.')
        import numpy as np
        with Image.open(image) as source:
            rgb=np.asarray(source.convert('RGB'))
            for row in rows:
                x0,y0,x1,y1=map(int,row['box']);region=rgb[max(0,y0):min(rgb.shape[0],y1),max(0,x0):min(rgb.shape[1],x1)]
                ink=region.min(axis=2)<220
                colored=(region.max(axis=2)-region.min(axis=2)>50)&ink
                row['heading']=row['box'][2]-row['box'][0]<secondary['width']*.6 and colored.sum()>max(1,ink.sum())*.25
        groups=[]
        for row in rows:
            previous=groups[-1][-1] if groups else None
            separated=previous and (row.get('heading') or previous.get('heading') or row['box'][1]-previous['box'][3]>max(20,(previous['box'][3]-previous['box'][1])*.5))
            if groups and not separated and len(groups[-1])<8 and row['box'][3]-groups[-1][0]['box'][1]<=700:groups[-1].append(row)
            else:groups.append([row])
        if len(groups)>30:raise RuntimeError('Too many text regions on one legacy page; split or crop this page first.')
        recovered=[]
        # A small context and short image strips keep the heavy stage bounded.
        with Image.open(image) as original,VisionRuntime('paddle',scratch,performance.page_workers(),context_size=2048) as runtime:
            for number,group in enumerate(groups):
                notify(f'Recovering Arabic · section {number+1} of {len(groups)}',progress=75)
                x0=max(0,int(min(r['box'][0] for r in group))-16);x1=min(original.width,math.ceil(max(r['box'][2] for r in group))+16)
                y0=max(0,int(min(r['box'][1] for r in group))-12);y1=min(original.height,math.ceil(max(r['box'][3] for r in group))+12)
                crop_path=scratch/'legacy-section.png'
                with original.crop((x0,y0,x1,y1)) as crop:
                    crop.thumbnail((1024,700));crop.save(crop_path)
                try:text=runtime.recognize(crop_path,'OCR:',max_tokens=768).strip()
                finally:crop_path.unlink(missing_ok=True)
                text=re.sub(r'(?m)^#{1,6}\s*','',text).replace('**','')
                text='\n'.join(line.strip() for line in text.splitlines() if line.strip())
                expected=sum(c.isalpha() for r in group for c in r['text'])
                actual=sum(c.isalpha() for c in text)
                if not text or actual<expected*.45:
                    raise RuntimeError('Detailed OCR did not recover enough text from an Arabic region.')
                recovered.append(dict(text=text,box=[x0,y0,x1,y1],score=.75,line_count=max(len(group),len(text.splitlines()))))
        return dict(width=secondary['width'],height=secondary['height'],rotation=0,rows=recovered,blocks=[],logical_ocr=True,detailed_ocr=True)
    finally:
        image.unlink(missing_ok=True)
        if result:result.unlink(missing_ok=True)
