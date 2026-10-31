"""Validated page plans and PDF-level assembly; no page rasterization on export."""
from collections import OrderedDict
import hashlib
from pathlib import Path
import shutil

import pymupdf

from yuzufile.resources import page_indices

MAX_PAGES = 2000
MAX_SOURCES = 50
MAX_BYTES = 1_000_000_000


def inspect_source(path):
    path = Path(path).resolve(strict=True)
    if path.suffix.lower() != '.pdf' or not path.is_file():
        raise ValueError('Choose a PDF file.')
    stat = path.stat()
    if stat.st_size > MAX_BYTES:
        raise ValueError('The combined input size must not exceed 1 GB.')
    with pymupdf.open(path) as document:
        validate_document(document)
        count = len(document)
    return {'path': str(path), 'pages': count, 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def validate_document(document):
    if not document.is_pdf or document.needs_pass:
        raise ValueError('Choose an unlocked, readable PDF.')
    if not 0 < len(document) <= MAX_PAGES:
        raise ValueError('Each PDF must contain 1–2,000 pages.')
    if document.get_sigflags() > 0:
        raise ValueError('This PDF contains signature fields. Use an unsigned copy to organize pages.')


def validate_plan(value):
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('The page arrangement is invalid. Open Organize pages again.')
    sources, pages = value.get('sources'), value.get('pages')
    if not isinstance(sources, list) or not 0 < len(sources) <= MAX_SOURCES:
        raise ValueError('Choose between 1 and 50 PDF files.')
    if not isinstance(pages, list) or not 0 < len(pages) <= MAX_PAGES:
        raise ValueError('The output must contain 1–2,000 pages.')
    clean_sources = []
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get('path'), str):
            raise ValueError('A source PDF is invalid.')
        if not Path(source['path']).is_absolute() or Path(source['path']).suffix.lower() != '.pdf':
            raise ValueError('Source PDFs must use absolute file paths.')
        if any(type(source.get(key)) is not int or source[key] < 0 for key in ('pages','size','mtime_ns')):
            raise ValueError('Source details are missing. Open Organize pages again.')
        if not 0 < source['pages'] <= MAX_PAGES:
            raise ValueError('A source PDF has an invalid page count.')
        clean_sources.append({key:source[key] for key in ('path','pages','size','mtime_ns')})
    clean_pages, used = [], []
    for page in pages:
        if not isinstance(page, dict) or any(type(page.get(k)) is not int for k in ('source','page','rotation')):
            raise ValueError('A selected page is invalid.')
        source, number, rotation = (page[k] for k in ('source','page','rotation'))
        if not 0 <= source < len(sources) or not 0 <= number < sources[source]['pages']:
            raise ValueError('A selected page does not exist in its source PDF.')
        if rotation not in (0,90,180,270):
            raise ValueError('Page rotation must be a multiple of 90 degrees.')
        if source not in used:
            used.append(source)
        clean_pages.append(dict(source=source, page=number, rotation=rotation))
    # Discard sources whose pages were all removed, including inaccessible files.
    if sum(clean_sources[index]['size'] for index in used) > MAX_BYTES:
        raise ValueError('The combined input size must not exceed 1 GB.')
    result={'version':1, 'sources':[clean_sources[i] for i in used],
            'pages':[{**p,'source':used.index(p['source'])} for p in clean_pages]}
    if value.get('action')=='merge':result['action']='merge'
    return result


def source_unchanged(source):
    try:
        stat = Path(source['path']).stat()
    except OSError:
        raise ValueError(f"Source PDF is unavailable: {Path(source['path']).name}. Add it again.") from None
    if (stat.st_size, stat.st_mtime_ns) != (source['size'], source['mtime_ns']):
        raise ValueError(f"Source PDF changed: {Path(source['path']).name}. Add it again before saving.")


def assemble_pdf(value, scratch, profile=None, notify=None):
    plan = validate_plan(value)
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=False)
    snapshots, information, warnings = [], [], []
    output = pymupdf.open()
    opened = OrderedDict()
    mapping = {}
    for target, page in enumerate(plan['pages']):
        mapping.setdefault((page['source'],page['page']), target)

    def document_for(index):
        if index in opened:
            opened.move_to_end(index)
            return opened[index]
        document = pymupdf.open(snapshots[index])
        opened[index] = document
        if len(opened) > 2:
            opened.popitem(last=False)[1].close()
        return document

    try:
        for index, source in enumerate(plan['sources']):
            source_unchanged(source)
            snapshot = scratch / f'source-{index}.pdf'
            shutil.copyfile(source['path'], snapshot)
            source_unchanged(source)
            with pymupdf.open(snapshot) as document:
                validate_document(document)
                if len(document) != source['pages']:
                    raise ValueError('The source page count changed. Add the PDF again.')
                if document.embfile_count():
                    warnings.append('Document attachments are not included in the organized PDF.')
            with snapshot.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            snapshots.append(snapshot)
            information.append({'name':Path(source['path']).name,'pages':source['pages'],'sha256':digest})
        missing_links = 0
        for target in page_indices(len(plan['pages']), profile, notify, 'Organizing pages', 2, 58):
            page = plan['pages'][target]
            source = document_for(page['source'])
            output.insert_pdf(source, from_page=page['page'], to_page=page['page'], links=False, widgets=True)
            output[target].set_rotation((source[page['page']].rotation + page['rotation']) % 360)
        # Link destinations become valid after every page has been inserted.
        for target, page in enumerate(plan['pages']):
            source = document_for(page['source'])
            for link in source[page['page']].get_links():
                new = {key:val for key,val in link.items() if key not in ('xref','id')}
                if link['kind'] == pymupdf.LINK_GOTO:
                    destination = mapping.get((page['source'],link.get('page',-1)))
                    if destination is None:
                        missing_links += 1
                        continue
                    new['page'] = destination
                try:
                    output[target].insert_link(new)
                except (ValueError,RuntimeError):
                    warnings.append('Some unsupported links could not be preserved. Check links in the output.')
        if missing_links:
            warnings.append(f'{missing_links} internal link(s) targeted excluded pages and were removed.')
        toc = []
        for index, source_info in enumerate(plan['sources']):
            source = document_for(index)
            level_offset = 1 if len(plan['sources']) > 1 else 0
            if level_offset:
                first = min(target for (src,_),target in mapping.items() if src==index)
                toc.append([1,Path(source_info['path']).stem,first+1])
            previous = level_offset
            for level, title, page_number in source.get_toc():
                destination = mapping.get((index,page_number-1))
                if destination is None:
                    continue
                adjusted = min(level+level_offset, previous+1)
                toc.append([adjusted,title,destination+1])
                previous = adjusted
        if toc:
            output.set_toc(toc)
        output.set_metadata(document_for(0).metadata)
        return output, {'sources':information,'output_pages':len(output),
                        'source_count':len(plan['sources']), 'rotated_pages':sum(p['rotation']!=0 for p in plan['pages']),
                        'page_map':plan['pages']}, list(dict.fromkeys(warnings))
    except Exception:
        output.close()
        raise
    finally:
        for document in opened.values():
            document.close()
