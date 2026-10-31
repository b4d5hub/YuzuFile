"""Regression fixture: identical rendered Arabic, deliberately wrong Unicode."""
from pathlib import Path
import json
import sys
from docx import Document
from yuzufile.worker import convert
from legacy_arabic_fixture import create

root=Path(sys.argv[1] if len(sys.argv)>1 else 'tmp/legacy-arabic-qa').absolute()
root.mkdir(exist_ok=True,parents=True)
source=create(root/'legacy-arabic.pdf')
before=source.read_bytes()
for name,languages in (('automatic',[]),('arabic-selected',['ara'])):
    convert(dict(root=str(root/name),source=str(source),mode='word',languages=languages,performance='low'))
    path=root/name/'result/document.docx'
    word=Document(path)
    text='\n'.join(p.text for p in word.paragraphs)
    assert 'تقرير المبيعات السنوي' in text and 'مرحبا بالعالم' in text,text
    report=json.loads(path.with_suffix('.quality.json').read_text(encoding='utf-8'))
    assert report['pages'][0]['legacy_arabic_recovered'] and report['pages'][0]['recovered_lines']==0
    (root/f'{name}.txt').write_text(text,encoding='utf-8')
assert source.read_bytes()==before
print(root)
