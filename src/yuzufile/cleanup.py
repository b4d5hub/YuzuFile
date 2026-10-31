"""Conservative page straightening and margin trimming, preserving PDF objects."""
from __future__ import annotations

import math
import os
from pathlib import Path

import pymupdf

from yuzufile.resources import page_indices
from yuzufile.spreads import selected_pages

MAX_ANGLE = 7
MAX_PIXELS = 3_000_000


def visual_edit(value):
    if not isinstance(value,dict):
        raise ValueError('Invalid visual page edit.')
    result={}
    if 'straighten' in value:
        if type(value['straighten']) is not bool:raise ValueError('Invalid page straightening option.')
        result['straighten']=value['straighten']
    if 'crop' in value:
        crop=value['crop']
        if crop is not None:
            if not isinstance(crop,(list,tuple)) or len(crop)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in crop):
                raise ValueError('The crop rectangle is invalid.')
            if not 0 <= crop[0] < crop[2] <= 1 or not 0 <= crop[1] < crop[3] <= 1:
                raise ValueError('Keep the crop rectangle inside the page.')
            crop=list(map(float,crop))
        result['crop']=crop
    if 'angle' in value:
        angle=value['angle']
        if angle is not None and (isinstance(angle,bool) or not isinstance(angle,(int,float)) or not math.isfinite(angle) or abs(angle)>45):
            raise ValueError('Manual straightening must stay between −45° and 45°.')
        result['angle']=float(angle) if angle is not None else None
    if 'rotation' in value:
        if type(value['rotation']) is not int or value['rotation'] not in (0,90,180,270):
            raise ValueError('Page rotation must be a quarter turn.')
        result['rotation']=value['rotation']
    return result


def visual_settings(value):
    if not isinstance(value,dict):
        raise ValueError('Invalid visual page options.')
    result={}
    if 'default' in value:result['default']=visual_edit(value['default'])
    files=value.get('files',{})
    if not isinstance(files,dict) or len(files)>2000:
        raise ValueError('Invalid visual document options.')
    clean_files={}
    for path,entry in files.items():
        if not isinstance(path,str) or not Path(path).is_absolute() or not isinstance(entry,dict):
            raise ValueError('Visual edits must identify their source PDF.')
        item={}
        if 'pages' in entry:
            item['pages']=str(entry['pages'])
            page_selection(item['pages'])
        if 'default' in entry:item['default']=visual_edit(entry['default'])
        edits=entry.get('edits',{})
        if not isinstance(edits,dict) or len(edits)>2000:
            raise ValueError('Invalid visual page edits.')
        item['edits']={}
        for number,edit in edits.items():
            if not isinstance(number,str) or not number.isdigit() or not 1<=int(number)<=2000:
                raise ValueError('Invalid edited page number.')
            item['edits'][str(int(number))]=visual_edit(edit)
        clean_files[str(Path(path).absolute())]=item
    if clean_files:result['files']=clean_files
    return result


def file_options(config,path):
    key=os.path.normcase(os.path.abspath(path)) if path else ''
    return next((v for k,v in config.get('visual',{}).get('files',{}).items()
                 if os.path.normcase(os.path.abspath(k))==key),{})


def edit_for(config,path,index):
    file=file_options(config,path)
    return {**config.get('visual',{}).get('default',{}),**file.get('default',{}),
            **file.get('edits',{}).get(str(index+1),{})}


def settings(value=None):
    value = value or {}
    if not isinstance(value, dict):
        raise ValueError('Choose valid page cleanup options.')
    straighten, trim = value.get('straighten', True), value.get('trim', True)
    visual=visual_settings(value.get('visual',{}))
    if type(straighten) is not bool or type(trim) is not bool or not (straighten or trim or visual):
        raise ValueError('Select straightening, margin trimming, or both.')
    padding = value.get('padding_mm', 3)
    if isinstance(padding, bool) or not isinstance(padding, (float, int)) or not math.isfinite(padding) or not 1 <= padding <= 20:
        raise ValueError('Margin padding must be between 1 and 20 mm.')
    pages = str(value.get('pages', '')).strip()
    page_selection(pages)
    result=dict(straighten=straighten, trim=trim, padding_mm=float(padding), pages=pages)
    if visual:result['visual']=visual
    return result


def page_selection(expression, count=None):
    try:
        return selected_pages(expression, count)
    except ValueError as error:
        raise ValueError(str(error).replace('split page range', 'cleanup page range')) from None


def _raster(page, longest=1600):
    import numpy as np
    scale = min(150/72, longest/max(page.rect.width,page.rect.height),
                math.sqrt(MAX_PIXELS/max(1,page.rect.get_area())))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csGRAY,
                         alpha=False,annots=True)
    gray = np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width).copy()
    return gray, pix.width/page.rect.width, pix.height/page.rect.height


def estimate_angle(page):
    """Return a CCW correction only when text-line evidence is consistent."""
    import cv2
    import numpy as np
    cv2.setNumThreads(1)
    area = page.rect.get_area()
    visual = any((pymupdf.Rect(i['bbox']) & page.rect).get_area() > area*.25
                 for i in page.get_image_info())
    directions = []
    if not visual:
        for block in page.get_text('dict',flags=0)['blocks']:
            for line in block.get('lines',[]):
                spans=line['spans']
                if sum(len(s['text'].strip()) for s in spans) < 8:
                    continue
                if any(any(k in s['font'].casefold() for k in ('glyphless','yuzufile','ocr')) for s in spans):
                    continue
                x,y=line['dir']
                angle=math.degrees(math.atan2(y,x))
                if abs(angle) <= MAX_ANGLE:
                    directions.append(angle)
        if len(directions) >= 3:
            median=float(np.median(directions))
            support=sum(abs(a-median)<.3 for a in directions)/len(directions)
            if support >= .8:
                return (round(median,2) if abs(median)>=.15 else 0), 'native baselines'
    gray,_,_=_raster(page,1000)
    binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV|cv2.THRESH_OTSU)[1]
    h,w=binary.shape
    border=max(2,min(h,w)//50)
    binary[:border]=0; binary[-border:]=0
    binary[:,:border]=0; binary[:,-border:]=0
    density=np.count_nonzero(binary)/binary.size
    if not .002 <= density <= .35:
        return 0, 'insufficient text-line evidence'
    # Long vertical rules and photographs can overwhelm horizontal projection.
    vertical=cv2.morphologyEx(binary,cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_RECT,(1,max(30,h//12))))
    binary=cv2.subtract(binary,vertical)
    def score(angle):
        matrix=cv2.getRotationMatrix2D((w/2,h/2),float(angle),1)
        aligned=cv2.warpAffine(binary,matrix,(w,h),flags=cv2.INTER_NEAREST,borderValue=0)
        sums=np.count_nonzero(aligned,axis=1).astype(np.float64)
        return float(np.dot(sums,sums))
    baseline=score(0)
    coarse=[(score(a),float(a)) for a in np.arange(-MAX_ANGLE,MAX_ANGLE+.01,.5)]
    _,best=max(coarse)
    refined=[(score(a),float(a)) for a in np.arange(max(-MAX_ANGLE,best-.4),min(MAX_ANGLE,best+.4)+.01,.1)]
    peak,angle=max(refined)
    if abs(angle)<.2 or abs(angle)>MAX_ANGLE-.15 or peak < baseline*1.18:
        return 0, 'no reliable small-angle correction'
    # Require a useful peak instead of choosing arbitrary edges of a flat curve.
    if peak < min(score(angle-1),score(angle+1))*1.08:
        return 0, 'ambiguous text-line direction'
    return round(angle,2), 'scan text-line projection'


def content_bounds(page, padding_mm):
    import cv2
    import numpy as np
    cv2.setNumThreads(1)
    gray,sx,sy=_raster(page)
    h,w=gray.shape
    border=max(1,min(h,w)//100)
    edges=np.concatenate((gray[:border].ravel(),gray[-border:].ravel(),
                          gray[:,:border].ravel(),gray[:,-border:].ravel()))
    background=float(np.percentile(edges,80))
    if background < 170:
        return page.rect, 'Dark page edges; automatic trimming was skipped.'
    mask=(gray < min(246,background-10)).astype(np.uint8)
    # Ignore isolated raster speckles, not small words, footnotes or page numbers.
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
    keep=np.zeros(count,dtype=np.uint8)
    keep[1:]=(stats[1:,cv2.CC_STAT_AREA]>=3)
    mask=keep[labels]
    points=cv2.findNonZero(mask)
    if points is None:
        return page.rect, 'Blank page; margins left unchanged.'
    x,y,bw,bh=cv2.boundingRect(points)
    rect=pymupdf.Rect(x/sx,y/sy,(x+bw)/sx,(y+bh)/sy)
    # Keep native and invisible OCR text even if its boxes differ from scan ink.
    for word in page.get_text('words'):
        rect |= pymupdf.Rect(word[:4]) & page.rect
    # Faint vector artwork and small embedded figures may be lighter than the
    # scan threshold. Preserve their PDF geometry rather than cutting them off.
    for image in page.get_image_info():
        bounds=pymupdf.Rect(image['bbox']) & page.rect
        if bounds.get_area() < page.rect.get_area()*.8:
            rect |= bounds
    for drawing in page.get_cdrawings():
        bounds=pymupdf.Rect(drawing['rect']) & page.rect
        colors=[c for c in (drawing.get('color'),drawing.get('fill')) if c is not None]
        visible=any(any(abs(v-1)>.0001 for v in color) for color in colors)
        background=bounds.get_area() >= page.rect.get_area()*.9 and drawing.get('color') is None
        if visible and not background:
            rect |= bounds
    for annot in page.annots() or []:
        rect |= annot.rect & page.rect
    if rect.get_area() < page.rect.get_area()*.003:
        return page.rect, 'Very little content; margins left unchanged.'
    padding=padding_mm*72/25.4
    rect=(rect+(-padding,-padding,padding,padding)) & page.rect
    if rect.width < 36 or rect.height < 36:
        return page.rect, 'Small content area; margins left unchanged.'
    if max(abs(a-b) for a,b in zip(rect,page.rect)) < 2:
        return page.rect, ''
    return rect, ''


def _normalize(page):
    if page.rotation:
        crop=page.cropbox
        page.set_cropbox(page.mediabox)
        crop *= page.rotation_matrix
        page.remove_rotation()
        page.set_cropbox(crop)


def transform_page(source, index, config, source_path=None, preview_uncropped=False):
    """One-page preview/export primitive. Caller owns the returned document."""
    config=settings(config)
    original=source[index]
    edit=edit_for(config,source_path or source.name,index)
    if list(original.widgets()):
        raise ValueError('A selected page has interactive form fields. Use a flattened copy before cleaning it.')
    normalized=pymupdf.open()
    normalized.insert_pdf(source,from_page=index,to_page=index,links=False)
    mapping=pymupdf.Matrix(original.rotation_matrix)
    warnings=[]
    try:
        page=normalized[0]
        _normalize(page)
        rotation=edit.get('rotation',0)
        if rotation:
            page.set_rotation(rotation)
            mapping *= page.rotation_matrix
            _normalize(page)
        if edit.get('angle') is not None:
            angle,method=edit['angle'],'manual alignment'
        else:
            angle,method=estimate_angle(page) if edit.get('straighten',config['straighten']) else (0,'disabled')
        if angle and list(page.annots() or []):
            warnings.append('Straightening skipped to preserve page annotations; trimming can still apply.')
            angle=0
        if angle:
            matrix=pymupdf.Matrix(-angle)
            bounds=page.rect*matrix
            matrix *= pymupdf.Matrix(1,0,0,1,-bounds.x0,-bounds.y0)
            rotated=pymupdf.open()
            try:
                target=rotated.new_page(width=bounds.width,height=bounds.height)
                target.show_pdf_page(target.rect,normalized,0,rotate=angle)
            except Exception:
                rotated.close()
                raise
            normalized.close()
            normalized=rotated
            page=normalized[0]
            mapping *= matrix
        full_size=[page.rect.width,page.rect.height]
        manual_crop=config['trim'] and edit.get('crop') is not None
        if manual_crop:
            x0,y0,x1,y1=edit['crop']
            clip=pymupdf.Rect(x0*page.rect.width,y0*page.rect.height,x1*page.rect.width,y1*page.rect.height)
            if clip.width < min(12,page.rect.width)-.01 or clip.height < min(12,page.rect.height)-.01:
                raise ValueError('The crop is too small. Drag its edges outwards.')
            note=''
        else:
            clip,note=content_bounds(page,config['padding_mm']) if config['trim'] else (page.rect,'')
        if note:
            warnings.append(note)
        trimmed=max(abs(a-b) for a,b in zip(clip,page.rect)) > (.001 if manual_crop else 1)
        crop_fraction=[clip.x0/page.rect.width,clip.y0/page.rect.height,clip.x1/page.rect.width,clip.y1/page.rect.height]
        expected=page.get_text(clip=clip) if manual_crop else original.get_text()
        if trimmed and not preview_uncropped:
            page.clip_to_rect(clip)
            for annotation in list(page.annots() or []):
                if not clip.intersects(annotation.rect):page.delete_annot(annotation)
                elif not clip.contains(annotation.rect):warnings.append('An annotation crosses the crop boundary; check it in the result.')
            offset=page.cropbox_position
            page.set_cropbox(clip+(offset.x,offset.y,offset.x,offset.y))
            mapping *= pymupdf.Matrix(1,0,0,1,-clip.x0,-clip.y0)
        if source.xref_get_key(original.xref,'PDFaiOCR')[1]=='true':
            normalized.xref_set_key(page.xref,'PDFaiOCR','true')
        detail={'page':index+1,'angle_degrees':angle,'straighten_method':method,'trimmed':trimmed,
                'changed':bool(angle or trimmed or rotation),'original_size':[original.rect.width,original.rect.height],
                'output_size':[clip.width,clip.height], 'warnings':warnings,'rotation':rotation,
                'full_size':full_size,'crop':crop_fraction,'manual_crop':bool(manual_crop)}
        # Repeated straightening should not silently lose hidden searchable text.
        from yuzufile.engines import _preserves_page_text
        if not _preserves_page_text(expected,page.get_text()):
            raise ValueError(f'Cleanup validation found missing text on page {index+1}. This page was not exported.')
        return normalized,detail,mapping
    except Exception:
        normalized.close()
        raise


def clean_document(source,config,scratch,profile=None,notify=None,source_path=None):
    config=settings(config)
    selected=page_selection(file_options(config,source_path or source.name).get('pages',config['pages']),len(source))
    # Disk copy retains document attachments and document-level metadata without
    # loading the whole PDF into a Python bytes buffer.
    target=Path(scratch)/'cleanup-working.pdf'
    source.save(target,garbage=0,deflate=False)
    output=pymupdf.open(target)
    details,warnings,mappings=[],[],{}
    try:
        for index in page_indices(len(source),profile,notify,'Cleaning pages',8,18):
            if index not in selected:
                continue
            one,detail,matrix=transform_page(source,index,config,source_path)
            try:
                details.append(detail)
                warnings += [f"Cleanup page {index+1}: {w}" for w in detail['warnings']]
                if detail['changed']:
                    output.delete_page(index)
                    output.insert_pdf(one,from_page=0,to_page=0,start_at=index,links=False)
                    mappings[index]=matrix
            finally:
                one.close()
        if mappings:
            # PyMuPDF's link insertion matrix omits crop offsets on rotated
            # pages. Temporarily expose their unrotated geometry while rebuilding
            # navigation; restore the display rotation before returning.
            rotations={i:output[i].rotation for i in range(len(output)) if output[i].rotation}
            for i in rotations:output[i].set_rotation(0)
            # Rebuild links after replacements, including links on unchanged
            # pages which point to a transformed page's coordinates.
            for index in range(len(output)):
                page=output[index]
                for link in page.get_links():
                    page.delete_link(link)
                matrix=mappings.get(index,pymupdf.Identity)
                visible=page.rect*page.derotation_matrix
                for link in source[index].get_links():
                    # get_links() reports displayed (rotated) coordinates;
                    # our transforms and insert_link() use unrotated coordinates.
                    rect=pymupdf.Rect(link['from'])*source[index].derotation_matrix*matrix & visible
                    if rect.is_empty:
                        warnings.append(f'Cleanup page {index+1}: a link outside the retained page was removed.')
                        continue
                    new={k:v for k,v in link.items() if k not in ('xref','id')}
                    new['from']=rect
                    if link['kind']==pymupdf.LINK_GOTO:
                        number=link.get('page',-1)
                        if not 0 <= number < len(output):
                            warnings.append('An unresolved internal link could not be preserved.')
                            continue
                        new['to']=pymupdf.Point(link.get('to',(0,0)))*source[number].derotation_matrix*mappings.get(number,pymupdf.Identity)
                    try:
                        page.insert_link(new)
                    except (ValueError,RuntimeError):
                        warnings.append('An unsupported PDF link could not be preserved.')
            toc=source.get_toc(simple=False)
            for entry in toc:
                dest=entry[3]
                dest.pop('xref',None)
                number=dest.get('page',entry[2]-1)
                if dest.get('kind')==pymupdf.LINK_GOTO and 0<=number<len(output) and 'to' in dest:
                    dest['to']=pymupdf.Point(dest['to'])*source[number].derotation_matrix*mappings.get(number,pymupdf.Identity)
            if toc:
                output.set_toc(toc)
                # set_toc() uses crop height rather than the full PDF matrix.
                # Write precise PDF-space destinations so cropped pages retain
                # the same anchor as ordinary internal links.
                for xref,entry in zip(output.get_outline_xrefs(),toc):
                    dest=entry[3];number=dest.get('page',entry[2]-1)
                    if dest.get('kind')!=pymupdf.LINK_GOTO or not 0<=number<len(output) or 'to' not in dest:continue
                    page=output[number];point=pymupdf.Point(dest['to'])*~page.transformation_matrix
                    zoom=float(dest.get('zoom',0))
                    output.xref_set_key(xref,'Dest','null')
                    output.xref_set_key(xref,'A',f'<< /S /GoTo /D [{page.xref} 0 R /XYZ {point.x} {point.y} {zoom}] >>')
            for i,rotation in rotations.items():output[i].set_rotation(rotation)
        return output,{'settings':config,'selected_pages':len(selected),
                      'straightened_pages':sum(bool(p['angle_degrees']) for p in details),
                      'trimmed_pages':sum(p['trimmed'] for p in details),'pages':details},list(dict.fromkeys(warnings))
    except Exception:
        output.close()
        raise
