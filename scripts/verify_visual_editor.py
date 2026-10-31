"""Developer visual QA: real crop gestures, geometry, output and screenshots."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import json
import pymupdf
from PySide6.QtCore import QPoint,Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from yuzufile.cleanup import settings,clean_document
from yuzufile.cleanup_preview import CleanupPreview
from yuzufile.storage import Store
from yuzufile.ui import Window,CompressionBox
from yuzufile.spread_preview import SpreadPreview
from yuzufile.spreads import settings as split_settings

root=Path(__file__).resolve().parents[1]/'tmp/visual-editor-qa'
root.mkdir(exist_ok=True)
app=QApplication([])
for name in ('segoeui.ttf','seguisb.ttf','segoeuib.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
store=Store(root/'library');view=Window(store);view.timer.stop()
source=Path(__file__).resolve().parents[1]/'tmp/cleanup-qa/native.pdf'
view.add_files([str(source)])
for code,card in view.operations.items():card.setChecked(code=='cleanup')
view.show();app.processEvents()
view.grab().save(str(root/'home.png'))
dialog=CleanupPreview(view,[source],settings({'straighten':False}),CompressionBox)
dialog.show();app.processEvents()
dialog.begin_edit();dialog.crop_live([.12,.1,.92,.94]);dialog.finish_edit();dialog.render_page()
for _ in range(4):dialog.thumb_timer.stop();dialog.render_thumbnail();app.processEvents()
dialog.grab().save(str(root/'crop-editor.png'))
config=dialog.config()
with pymupdf.open(source) as doc:
    output,detail,warnings=clean_document(doc,config,root)
    with output:output.save(root/'visually-cropped.pdf')
dialog.tool('straighten');dialog.grab().save(str(root/'alignment-editor.png'))
dialog.resize(810,650);app.processEvents();dialog.grab().save(str(root/'compact-editor.png'))
dialog.reject()
split=SpreadPreview(view,[source],split_settings(dict(parts=3,cuts=[25,70])),CompressionBox)
split.show();app.processEvents();split.grab().save(str(root/'split-editor.png'));split.reject()
(root/'report.json').write_text(json.dumps({'cleanup':detail,'warnings':warnings},indent=2),encoding='utf-8')
view.supervisor.shutdown();view.close();store.close()
print(root)
