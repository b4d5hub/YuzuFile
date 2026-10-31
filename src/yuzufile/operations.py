"""Stable history modes for all nonempty operation combinations."""

MODES = {
    "pdf": frozenset({"ocr"}),
    "markdown": frozenset({"markdown"}),
    "both": frozenset({"ocr", "markdown"}),
    "compress": frozenset({"compress"}),
    "ocr_compress": frozenset({"ocr", "compress"}),
    "markdown_compress": frozenset({"markdown", "compress"}),
    "all": frozenset({"ocr", "markdown", "compress"}),
}
for _mode, _operations in list(MODES.items()):
    MODES['split_' + _mode] = _operations | {'split'}
MODES['split'] = frozenset({'split'})
# Preserve every existing history identifier and add Word combinations.
for _mode, _operations in list(MODES.items()):
    MODES[_mode + '_word'] = _operations | {'docx'}
MODES['word'] = frozenset({'docx'})
for _mode, _operations in list(MODES.items()):
    MODES[_mode + '_cleanup'] = _operations | {'cleanup'}
MODES['cleanup'] = frozenset({'cleanup'})
# Image-only output is independent of recognition. Preserve the identifiers of
# every older job, and add only compatible preprocessing/compression variants.
for _mode, _operations in list(MODES.items()):
    if _operations <= {'cleanup','split','compress'}:
        MODES['remove_ocr_' + _mode] = _operations | {'remove_ocr'}
MODES['remove_ocr'] = frozenset({'remove_ocr'})
MODES['organize'] = frozenset({'organize'})


def mode_for(operations) -> str:
    selected = frozenset(operations)
    if 'remove_ocr' in selected and selected & {'ocr','markdown','docx'}:
        raise ValueError('Remove OCR creates an image-only PDF. Select OCR, Word or Markdown separately; these tools clean old OCR automatically.')
    for mode, values in MODES.items():
        if values == selected:
            return mode
    raise ValueError("Select at least one operation")


def mode_label(mode: str) -> str:
    selected = MODES.get(mode, ())
    return " + ".join(title for code, title in
                      (("organize", "Organize pages"), ("cleanup", "Clean up scans"), ("split", "Split spreads"), ('remove_ocr','Remove OCR'), ("ocr", "OCR"), ("markdown", "Markdown"), ("docx", "Word"), ("compress", "Compress"))
                      if code in selected) or mode
