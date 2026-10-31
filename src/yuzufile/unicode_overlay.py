"""Normalize Arabic presentation glyph mappings in invisible OCR overlays."""
import re
import unicodedata


def _presentation(code):
    return 0xfb50 <= code <= 0xfdff or 0xfe70 <= code <= 0xfeff


def _needs_normalization(code):
    return _presentation(code) or code == 0xa0


def _unicode_hex(value):
    text = bytes.fromhex(value).decode('utf-16-be')
    return ''.join(unicodedata.normalize('NFKC', c) if _needs_normalization(ord(c)) else c
                   for c in text).encode('utf-16-be').hex()


def normalize_cmap(source):
    """Preserve glyph IDs and rendering; change only Arabic Unicode values.

    MuPDF's fallback Arabic font maps glyphs to presentation-form code points.
    Standard Arabic values allow ordinary search/copy without caller-side NFKC.
    Range arrays support ligatures whose normalized value has several letters.
    """
    def ranges(block):
        def row(match):
            first, last, initial = (int(s, 16) for s in match.groups())
            if last < first or last - first > 65535:
                return match[0]
            if not any(_needs_normalization(initial + n) for n in range(last - first + 1)):
                return match[0]
            values = ['<' + _unicode_hex(f'{initial + n:04x}') + '>'
                      for n in range(last - first + 1)]
            return f'<{match[1]}> <{match[2]}> [' + ' '.join(values) + ']'
        return re.sub(r'(?m)^[ \t]*<([\da-fA-F]+)>[ \t]*<([\da-fA-F]+)>[ \t]*<([\da-fA-F]+)>[ \t]*$', row, block[0])

    def characters(block):
        def row(match):
            decoded = bytes.fromhex(match[2]).decode('utf-16-be')
            if not any(_needs_normalization(ord(c)) for c in decoded):
                return match[0]
            return f'<{match[1]}> <{_unicode_hex(match[2])}>'
        return re.sub(r'(?m)^[ \t]*<([\da-fA-F]+)>[ \t]*<([\da-fA-F]+)>[ \t]*$', row, block[0])

    result = re.sub(r'\d+ beginbfrange\b.*?endbfrange', ranges, source, flags=re.S)
    return re.sub(r'\d+ beginbfchar\b.*?endbfchar', characters, result, flags=re.S)


def normalize_arabic_fonts(page):
    document = page.parent
    seen = set()
    for font in page.get_fonts(full=True):
        kind, value = document.xref_get_key(font[0], 'ToUnicode')
        if kind != 'xref':
            continue
        xref = int(value.split()[0])
        if xref in seen:
            continue
        seen.add(xref)
        original = document.xref_stream(xref)
        if not original:
            continue
        try:
            normalized = normalize_cmap(original.decode('ascii')).encode('ascii')
        except (UnicodeError, ValueError):
            continue  # An unrelated source font may use a different CMap form.
        if normalized != original:
            document.update_stream(xref, normalized)
