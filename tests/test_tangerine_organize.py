"""Focused document ordering and page-dominant visual workspaces."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import pymupdf,pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from yuzufile.merge_ui import MergeDialog
from yuzufile.organize_ui import OrganizeDialog
from yuzufile.page_preview import PagePreview


@pytest.fixture
def documents(tmp_path):
    app=QApplication.instance() or QApplication([])
    paths=[]
    for name,count in (('First book',3),('Second book',2)):
        path=tmp_path/(name+'.pdf')
        with pymupdf.open() as doc:
            for number in range(count):doc.new_page(width=400,height=560).insert_text((40,70),f'{name} {number+1}')
            doc.save(path)
        paths.append(path)
    return app,paths


def test_merge_document_order_builds_a_complete_page_plan_without_touching_sources(documents):
    app,paths=documents;before=[p.read_bytes() for p in paths]
    dialog=MergeDialog(None,paths);dialog.show();app.processEvents()
    try:
        assert dialog.merge_button.isEnabled() and dialog.documents.count()==2
        dialog.move_document(1,-1)
        assert [s['path'] for s in dialog.sources]==[str(paths[1]),str(paths[0])]
        assert not dialog.grab().isNull()
        dialog.finish();plan=dialog.result_plan
        assert plan['action']=='merge'
        assert [Path(s['path']).name for s in plan['sources']]==['Second book.pdf','First book.pdf']
        assert [(p['source'],p['page']) for p in plan['pages']]==[(0,0),(0,1),(1,0),(1,1),(1,2)]
        assert all(p['rotation']==0 for p in plan['pages'])
    finally:dialog.reject()
    assert before==[p.read_bytes() for p in paths]


def test_merge_failure_preserves_document_order_and_waits_for_two_files(documents,tmp_path):
    app,paths=documents;dialog=MergeDialog(None,[paths[0]])
    try:
        assert not dialog.merge_button.isEnabled();dialog.finish();assert dialog.result_plan is None
        invalid=tmp_path/'Invalid.pdf';invalid.write_bytes(b'broken')
        before=dialog.sources;dialog.add_files([paths[1],invalid])
        assert dialog.sources==before and dialog.message.text()
        dialog.add_files([paths[1]]);assert dialog.merge_button.isEnabled()
        dialog.remove_document(0);assert not dialog.merge_button.isEnabled()
    finally:dialog.reject()


def test_merge_row_arrow_and_remove_targets_act_on_the_clicked_document(documents):
    app,paths=documents;dialog=MergeDialog(None,paths);dialog.show();app.processEvents()
    try:
        rect=dialog.documents.visualItemRect(dialog.documents.item(1))
        up,_,_=dialog.documents.itemDelegate().controls(rect)
        QTest.mouseClick(dialog.documents.viewport(),Qt.MouseButton.LeftButton,pos=up.center().toPoint())
        assert dialog.sources[0]['path']==str(paths[1])
        rect=dialog.documents.visualItemRect(dialog.documents.item(0))
        _,_,remove=dialog.documents.itemDelegate().controls(rect)
        QTest.mouseClick(dialog.documents.viewport(),Qt.MouseButton.LeftButton,pos=remove.center().toPoint())
        assert [s['path'] for s in dialog.sources]==[str(paths[0])]
    finally:dialog.reject()


def test_card_rotate_keeps_selection_and_undo_reverses_only_that_change(documents):
    app,paths=documents;dialog=OrganizeDialog(None,[paths[0]]);dialog.show();app.processEvents()
    try:
        dialog.grid.item(0).setSelected(True);dialog.grid.item(1).setSelected(True)
        index=dialog.grid.model().index(2,0)
        rect=dialog.grid.itemDelegate().rotate_rect(dialog.grid.visualItemRect(dialog.grid.item(2)),index)
        QTest.mouseClick(dialog.grid.viewport(),Qt.MouseButton.LeftButton,pos=rect.center().toPoint())
        assert [p['rotation'] for p in dialog.entries()]==[0,0,90]
        assert dialog.selected()==[0,1]
        dialog.undo();assert [p['rotation'] for p in dialog.entries()]==[0,0,0]
    finally:dialog.reject()


def test_arrange_and_reader_prioritize_the_page_canvas_and_small_windows_fit(documents):
    app,paths=documents;dialog=OrganizeDialog(None,[paths[0]])
    dialog.resize(1200,900);dialog.show();app.processEvents()
    try:
        assert dialog.header.height()==48 and dialog.grid.height()>dialog.height()*.7
        assert dialog.message.isHidden() and dialog.destination.isHidden()
        dialog.resize(540,580);app.processEvents()
        assert dialog.width()==540
        assert dialog.grid.width()>=dialog.width()*.88
        reader=PagePreview(dialog,dialog.sources,dialog.entries());reader.resize(720,700);reader.show();app.processEvents()
        try:
            assert reader.view.height()>reader.height()*.7 and reader.caption.isHidden()
            assert not reader.grab().isNull()
        finally:reader.reject()
    finally:dialog.reject()
