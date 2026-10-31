"""Capture the current resident UI, not the legacy backing Window.

Run from the repository root with the prepared development environment.
Uses synthetic PDF content and an isolated temporary store; no conversions run.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import pymupdf
from PySide6.QtCore import QMimeData, QPoint, QUrl, Qt
from PySide6.QtGui import QDragEnterEvent, QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from yuzufile import __version__
from yuzufile.storage import Store
from yuzufile.ui import Window, CompressionBox
from yuzufile.shaped_shell import FloatingShell
from yuzufile.desktop_drag import DesktopDropWheel
from yuzufile.system_tray import TrayController
from yuzufile.organize_ui import OrganizeDialog
from yuzufile.cleanup_preview import CleanupPreview
from yuzufile.cleanup import settings as cleanup_settings
from yuzufile.spread_preview import SpreadPreview
from yuzufile.spreads import settings as split_settings


def sample(path):
    with pymupdf.open() as doc:
        for i, title in enumerate(('Project overview', 'Schedule and milestones', 'Review checklist')):
            page = doc.new_page(width=842, height=595)
            for x, heading in ((48, title), (450, 'Notes and next steps')):
                page.insert_text((x, 60), 'FIELD NOTES', fontsize=10, color=(.45,.45,.45))
                page.insert_text((x, 98), heading, fontsize=21)
                page.draw_line((x, 116), (x+335,116), color=(.8,.8,.8))
                for j, text in enumerate(('A small team working toward a shared goal.',
                        'Review the draft and collect feedback.', 'Keep decisions clear and easy to find.',
                        'Confirm the next milestone before delivery.')):
                    page.insert_text((x, 151+j*27), text, fontsize=12)
                for j, (label, value) in enumerate((('Preparation','Complete'),('Design review','In progress'),('Delivery','Next week'))):
                    y=300+j*42
                    page.draw_rect(pymupdf.Rect(x,y,x+335,y+42),color=(.8,.8,.8))
                    page.insert_text((x+12,y+26),label,fontsize=12)
                    page.insert_text((x+210,y+26),value,fontsize=12)
            page.insert_text((48,555), f'Sample document / {i+1}', fontsize=10)
        doc.save(path)


def main():
    output=ROOT/'docs/screenshots/current'
    output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setStyle('Fusion');app.setQuitOnLastWindowClosed(False)
    for name in ('segoeui.ttf','seguisb.ttf','segoeuib.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
    app.setFont(QFont('Segoe UI',10))
    captures={}
    def capture(widget,name,wait=200):
        widget.show();app.processEvents();QTest.qWait(wait)
        target=output/(name+'.png')
        assert widget.grab().save(str(target)), target
        captures[name]={'widget':type(widget).__name__,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}

    (ROOT/'tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='yuzufile-readme-',dir=ROOT/'tmp') as temp:
        temp=Path(temp);source=temp/'Field notes.pdf';sample(source)
        store=Store(temp/'library');view=Window(store);view.timer.stop()
        shell=FloatingShell(view);tray=TrayController(app,view,shell)
        # Offscreen Qt has no OS tray. Set resident state without registering one.
        tray._active=True;shell.tray_controller=tray;shell.enter_resident_mode()
        wheel=DesktopDropWheel(view)
        try:
            tray.refresh_actions();capture(tray.menu,'tray-menu');tray.menu.hide()
            wheel.arm(QPoint(400,300))
            mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(source))])
            event=QDragEnterEvent(QPoint(190,190),Qt.DropAction.CopyAction,mime,
                Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier)
            wheel.dragEnterEvent(event);assert event.isAccepted()
            capture(wheel,'tool-wheel');wheel.cancel()
            for code,name in (('docx','word-export'),('compress','compress-options')):
                shell.open_tool(code,[str(source)] if not view.pending else None)
                capture(shell,name);shell.hide()
            arrange=OrganizeDialog(view,[source]);arrange.resize(1000,600);arrange.page_size.setValue(260)
            capture(arrange,'workspace',1000);arrange.close()
            split=SpreadPreview(view,[source],split_settings({'parts':2,'cuts':[50]}),CompressionBox)
            split.resize(1000,700);capture(split,'split-editor',500);split.close()
            cleanup=CleanupPreview(view,[source],cleanup_settings({'straighten':False}),CompressionBox)
            cleanup.resize(1000,700);capture(cleanup,'cleanup-editor',500);cleanup.close()
        finally:
            wheel.cancel();tray.shutdown();shell._closed=True;shell.hide()
            view.supervisor.shutdown();view._closed=True;view.close();store.close()
    modules=('ui','shaped_shell','desktop_drag','system_tray','organize_ui','spread_preview','cleanup_preview','ui_style')
    manifest={'version':__version__,'capture':'Qt widget grabs from current resident surfaces; synthetic sample; no UI retouching',
        'source_sha256':{m:hashlib.sha256((ROOT/'src/yuzufile'/f'{m}.py').read_bytes()).hexdigest() for m in modules},'screenshots':captures}
    (output/'capture.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'Captured {len(captures)} current UI surfaces for {__version__}.')


if __name__=='__main__':main()
