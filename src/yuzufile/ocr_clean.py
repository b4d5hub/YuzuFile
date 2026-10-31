"""Image-only page preparation; old text and PDF resources never enter outputs."""
from __future__ import annotations
import math
from pathlib import Path
import pymupdf
from yuzufile.resources import trim_cache

MAX_PIXELS=8_000_000
RENDER_DPI=300


class DiskBackedDocument:
    """Spill completed pages incrementally; keep only one raster in flight."""
    def __init__(self,scratch:Path,limit_bytes=32_000_000):
        self._document=pymupdf.open();self.path=Path(scratch)/'prepared-pages.pdf'
        self.pending_bytes=0;self.limit_bytes=limit_bytes;self.checkpoints=0

    def __getattr__(self,name):return getattr(self._document,name)
    def __len__(self):return len(self._document)
    def __getitem__(self,index):return self._document[index]
    def __iter__(self):return iter(self._document)

    def note_stream_bytes(self,count):self.pending_bytes+=count

    def checkpoint(self,force=False):
        if not len(self) or not (force or self.pending_bytes>=self.limit_bytes):return
        if self.path.exists() and self._document.can_save_incrementally():
            self._document.save(self.path,incremental=True,deflate=True,encryption=pymupdf.PDF_ENCRYPT_KEEP)
        else:self._document.save(self.path,garbage=3,deflate=True)
        self._document.close();trim_cache();self._document=pymupdf.open(self.path)
        self.pending_bytes=0;self.checkpoints+=1

    def detach(self):
        self.checkpoint(force=True);document=self._document;self._document=None
        return document

    def close(self):
        if self._document is not None:self._document.close();self._document=None


class PreparedPageSource:
    """A known page count backed by pages prepared just before Word needs them."""
    def __init__(self,prepared,count):self.prepared=prepared;self.count=count
    def __len__(self):return self.count
    def __getitem__(self,index):return self.prepared[index]
    def __getattr__(self,name):return getattr(self.prepared,name)


def clean_page(source_page,target_document):
    """Append a lossless raster of the visible page, without old text/metadata."""
    checkpoint=getattr(target_document,'checkpoint',None)
    if checkpoint is not None:checkpoint()
    rect=source_page.rect
    if rect.is_empty or rect.is_infinite:raise ValueError('This page has invalid dimensions.')
    scale=min(RENDER_DPI/72,math.sqrt(MAX_PIXELS/max(1,rect.get_area())),10_000/max(rect.width,rect.height))
    while math.ceil(rect.width*scale)*math.ceil(rect.height*scale)>MAX_PIXELS:scale*=.999
    pix=source_page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csRGB,alpha=False,annots=True)
    try:
        page=target_document.new_page(width=rect.width,height=rect.height)
        image=page.insert_image(page.rect,pixmap=pix)
        # PyMuPDF otherwise retains decoded RGB (~24 MB per page). Compress the
        # actual image stream immediately, before preparing another page.
        target_document.update_stream(image,pix.samples,compress=True)
        note=getattr(target_document,'note_stream_bytes',None)
        if note is not None:note(len(target_document.xref_stream_raw(image)))
        target_document.xref_set_key(page.xref,'PDFaiImageOnly','true')
        if page.get_text().strip() or page.get_fonts():raise ValueError('Image-only page validation found a text resource.')
        return {'render_dpi':round(72*scale,2),'pixels':pix.width*pix.height,
                'width':rect.width,'height':rect.height,'text_removed':bool(source_page.get_text().strip())}
    finally:del pix


def copy_navigation(source,target):
    """Keep local/URI navigation, without copying source page content or forms."""
    warnings=[]
    toc=source.get_toc(simple=False)
    if toc:
        try:target.set_toc(toc)
        except (ValueError,RuntimeError):
            target.set_toc(source.get_toc());warnings.append('Bookmark titles were retained; detailed destinations were simplified.')
    for index in range(len(source)):
        for value in source[index].get_links():
            if value['kind'] not in (pymupdf.LINK_GOTO,pymupdf.LINK_URI):continue
            link={key:value[key] for key in ('kind','from','page','to','uri','zoom') if key in value}
            try:target[index].insert_link(link)
            except (ValueError,RuntimeError):warnings.append(f'Page {index+1}: a navigation link could not be retained.')
    return list(dict.fromkeys(warnings))


def image_only_document(source,scratch,notify=None,performance=None):
    holder=DiskBackedDocument(scratch);removed=0;maximum=0
    try:
        for index in range(len(source)):
            if notify:notify(f'Removing OCR · page {index+1} of {len(source)}',page=index+1,progress=round(8+52*index/max(1,len(source))))
            details=clean_page(source[index],holder);removed+=details['text_removed'];maximum=max(maximum,details['pixels'])
            trim_cache()
        warnings=copy_navigation(source,holder)
        output=holder.detach()
        return output,{'pages':len(source),'pages_with_old_text':removed,'image_only':True,
                       'render_dpi':RENDER_DPI,'max_pixels':maximum,'page_workers':1,
                       'checkpoints':holder.checkpoints},warnings
    finally:holder.close()


def validate_image_only(document):
    for index in range(len(document)):
        if document[index].get_text().strip() or document[index].get_fonts():
            raise ValueError(f'Image-only validation found text on page {index+1}.')
