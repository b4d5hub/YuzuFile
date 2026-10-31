"""Name published documents after their source and the operations they contain."""
from pathlib import Path


_PDF_FEATURES=('cleanup','split','remove_ocr','ocr','compress','merge','organize')
_LABELS={'organize':'arrange','docx':'word'}
_DOCUMENTS={
    'document.ocr.pdf':'pdf','document.compressed.pdf':'pdf',
    'document.no-ocr.pdf':'pdf','document.cleaned.pdf':'pdf',
    'document.split.pdf':'pdf','document.organized.pdf':'pdf',
    'document.md':'markdown','document.docx':'docx',
    'document.quality.json':'report',
}


def output_name(source,operations,kind):
    selected=set(operations)
    if kind=='pdf':features=[code for code in _PDF_FEATURES if code in selected];extension='.pdf'
    elif kind in {'markdown','docx','report'}:
        features=[code for code in ('cleanup','split') if code in selected]
        features.append('markdown' if kind=='markdown' else 'docx')
        extension={'markdown':'.md','docx':'.docx','report':'.quality.json'}[kind]
    else:raise ValueError('Unknown document output type.')
    if not features:raise ValueError('Select a feature for the PDF output name.')
    suffix='_'+'_'.join(_LABELS.get(code,code) for code in features)+extension
    stem=Path(source).stem.rstrip(' .') or 'PDF'
    # Preserve the complete source name whenever possible. Windows limits each
    # filename component to 255 UTF-16 units, including the feature and extension.
    while len((stem+suffix).encode('utf-16-le'))//2>255:stem=stem[:-1]
    return stem+suffix


def rename_outputs(staging,source,operations,artifacts):
    """Rename only completed documents before publishing the result manifest.

    Engines keep their private working names. Relative Markdown asset links,
    license notices and old History entries do not need any modification.
    """
    staging=Path(staging);plans=[];published=[];targets=set()
    for artifact in artifacts:
        name=Path(artifact['path']).name
        if name not in _DOCUMENTS or artifact['kind']!=_DOCUMENTS[name]:
            published.append(dict(artifact));continue
        original=staging/name
        target=staging/output_name(source,operations,artifact['kind'])
        if not original.is_file():raise ValueError('A completed output is missing before naming.')
        if target in targets or (target!=original and target.exists()):
            raise ValueError('An output filename is already in use.')
        targets.add(target);plans.append((original,target))
        published.append({**artifact,'path':'result/'+target.name})
    for original,target in plans:
        if original!=target:original.rename(target)
    return published
