"""PDF-level spread division, with bounded traversal and visible-page ordering."""
import math
import re

import pymupdf

from yuzufile.resources import page_indices

DIRECTIONS = {"rl": "Right → Left", "lr": "Left → Right",
              "tb": "Top → Bottom", "bt": "Bottom → Top"}
MAX_PARTS = 12
MAX_OUTPUT_PAGES = 4000


def settings(value=None):
    value = value or {}
    direction = value.get("direction", "lr")
    position = float(value.get("position", 50))
    pages = str(value.get("pages", "")).strip()
    parts = value.get('parts', 2)
    if isinstance(parts, bool) or not isinstance(parts, int) or not 2 <= parts <= MAX_PARTS:
        raise ValueError(f'Choose between 2 and {MAX_PARTS} parts per page.')
    if direction not in DIRECTIONS:
        raise ValueError("Choose a valid spread order.")
    if not math.isfinite(position) or not 5 <= position <= 95:
        raise ValueError("The split position must be between 5% and 95%.")
    selected_pages(pages)
    result={"direction": direction, "position": position, "pages": pages, 'parts': parts}
    if value.get('cuts') is not None:
        cuts=value['cuts']
        if not isinstance(cuts,(tuple,list)) or len(cuts)!=parts-1 or any(isinstance(c,bool) or not isinstance(c,(int,float)) or not math.isfinite(c) for c in cuts):
            raise ValueError('Each split needs one dividing line between adjacent parts.')
        boundaries=[0,*cuts,100]
        minimum=5 if parts==2 else 2
        if any(b-a<minimum-.00001 for a,b in zip(boundaries,boundaries[1:])):
            raise ValueError(f'Keep dividing lines in order and at least {minimum}% apart.')
        result['cuts']=list(map(float,cuts))
        if parts==2:result['position']=float(cuts[0])
    return result


def selected_pages(expression, count=None):
    if not expression or expression.lower() == "all":
        return set(range(count)) if count is not None else None
    result = set()
    for part in expression.split(","):
        match = re.fullmatch(r"\s*([1-9]\d*)(?:\s*-\s*([1-9]\d*))?\s*", part)
        if not match:
            raise ValueError("Use page ranges such as 2-15, 18, or leave blank for all pages.")
        first = int(match[1])
        last = int(match[2] or first)
        if first > last or last > 2000 or (count is not None and last > count):
            raise ValueError("The split page range is outside the PDF or is reversed.")
        result.update(range(first - 1, last))
    return result


def halves(rect, config):
    """Ordered sections; legacy name retained for existing integrations."""
    rect = pymupdf.Rect(rect)
    parts = config.get('parts', 2)
    boundaries = [0,*[c/100 for c in config['cuts']],1] if 'cuts' in config else ([0, config['position'] / 100, 1] if parts == 2 else [n / parts for n in range(parts + 1)])
    if config["direction"] in {"lr", "rl"}:
        pair = [pymupdf.Rect(rect.x0 + rect.width*a, rect.y0, rect.x0 + rect.width*b, rect.y1)
                for a,b in zip(boundaries, boundaries[1:])]
    else:
        pair = [pymupdf.Rect(rect.x0, rect.y0 + rect.height*a, rect.x1, rect.y0 + rect.height*b)
                for a,b in zip(boundaries, boundaries[1:])]
    return pair[::-1] if config["direction"] in {"rl", "bt"} else pair


def split_document(source, config, profile=None, notify=None):
    config = settings(config)
    selected = selected_pages(config["pages"], len(source))
    if len(source) + len(selected) * (config['parts'] - 1) > MAX_OUTPUT_PAGES:
        raise ValueError('Splitting would exceed 4,000 output pages. Choose fewer pages or parts.')
    output = pymupdf.open()
    mapping, links, warnings = {}, [], []
    try:
        for index in page_indices(len(source), profile, notify, "Splitting spreads", 8, 20):
            original = source[index]
            if index not in selected:
                target = len(output)
                output.insert_pdf(source, from_page=index, to_page=index, links=False)
                mapping[index] = [(target, original.rect, original.rotation_matrix, pymupdf.Point(0, 0))]
                links.append((index, original.get_links()))
                continue
            if list(original.widgets()):
                raise ValueError("A selected spread contains interactive form fields. Flatten the form in a PDF editor before splitting it.")
            with pymupdf.open() as normalized:
                normalized.insert_pdf(source, from_page=index, to_page=index, links=False)
                page = normalized[0]
                if page.rotation:
                    # remove_rotation resets the crop box to the media box.
                    # Rotate the original crop in full-page coordinates first.
                    crop = page.cropbox
                    page.set_cropbox(page.mediabox)
                    crop *= page.rotation_matrix
                    page.remove_rotation()
                    page.set_cropbox(crop)
                parts = halves(page.rect, config)
                links.append((index, original.get_links()))
                mapping[index] = []
                for clip in parts:
                    target = len(output)
                    output.insert_pdf(normalized, links=False)
                    half = output[target]
                    # clip_to_rect removes opposite-half content, including hidden
                    # OCR text; a crop box alone would only hide it visually.
                    half.clip_to_rect(clip)
                    for annotation in list(half.annots() or []):
                        if not annotation.rect.intersects(clip):
                            half.delete_annot(annotation)
                        elif not clip.contains(annotation.rect):
                            warnings.append("An annotation crosses the split line; check it in the output PDF.")
                    offset = half.cropbox_position
                    crop = clip + (offset.x, offset.y, offset.x, offset.y)
                    half.set_cropbox(crop)
                    mapping[index].append((target, clip, original.rotation_matrix, pymupdf.Point(clip.x0, clip.y0)))
        # Restore links after all target page numbers are known.
        for index, entries in links:
            original = source[index]
            for link in entries:
                for target, clip, matrix, offset in mapping[index]:
                    rect = pymupdf.Rect(link['from']) * matrix
                    if not clip.intersects(rect):
                        continue
                    rect = rect & clip
                    new = {k: v for k, v in link.items() if k not in {'xref', 'id'} }
                    if index in selected:
                        rect += (-offset.x, -offset.y, -offset.x, -offset.y)
                    else:
                        rect *= original.derotation_matrix
                    new['from'] = rect
                    if link['kind'] == pymupdf.LINK_GOTO:
                        destination = link.get('page', -1)
                        if destination not in mapping:
                            warnings.append("A named or unresolved internal link could not be remapped.")
                            continue
                        point = pymupdf.Point(link.get('to', (0, 0))) * source[destination].rotation_matrix
                        entry = next((part for part in mapping[destination] if part[1].contains(point)), mapping[destination][0])
                        new['page'] = entry[0]
                        new['to'] = point - entry[3] if destination in selected else point * source[destination].derotation_matrix
                    try:
                        output[target].insert_link(new)
                    except (ValueError, RuntimeError):
                        warnings.append("A PDF link could not be preserved; check links in the output.")
        toc = source.get_toc()
        for entry in toc:
            if entry[2] > 0:
                entry[2] = mapping[entry[2] - 1][0][0] + 1
        if toc:
            output.set_toc(toc)
        output.set_metadata(source.metadata)
        return output, {"input_pages": len(source), "split_pages": len(selected),
                        "output_pages": len(output), **config}, list(dict.fromkeys(warnings))
    except Exception:
        output.close()
        raise
