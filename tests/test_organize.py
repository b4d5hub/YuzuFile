from pathlib import Path

import pymupdf
import pytest

from yuzufile.organize import assemble_pdf, inspect_source, validate_plan
from artifact_helpers import artifact_path


@pytest.fixture
def book(tmp_path):
    path=tmp_path/'Book.pdf'
    with pymupdf.open() as document:
        for number in range(1,5):
            page=document.new_page(width=300,height=400)
            page.insert_text((40,70),f'Page {number}',fontsize=24)
        document.save(path)
    return path


def plan_for(path, numbers):
    return {'version':1,'sources':[inspect_source(path)],
            'pages':[{'source':0,'page':n,'rotation':0} for n in numbers]}


def test_extract_pages_keeps_order_and_source(book,tmp_path):
    original=book.read_bytes()
    output,details,_=assemble_pdf(plan_for(book,[3,1]),tmp_path/'snapshots')
    with output:
        assert [p.get_text().strip() for p in output]==['Page 4','Page 2']
        assert details['output_pages']==2
        with pymupdf.open(book) as source:
            assert output[0].get_pixmap().samples==source[3].get_pixmap().samples
    assert book.read_bytes()==original


def test_invalid_and_empty_page_plans(book):
    plan=plan_for(book,[])
    with pytest.raises(ValueError,match='output must contain'):
        validate_plan(plan)
    plan=plan_for(book,[0]);plan['pages'][0]['page']=10
    with pytest.raises(ValueError,match='does not exist'):
        validate_plan(plan)


def test_changed_or_missing_source_fails_cleanly(book,tmp_path):
    plan=plan_for(book,[0])
    book.write_bytes(book.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='changed'):
        assemble_pdf(plan,tmp_path/'changed')
    book.unlink()
    with pytest.raises(ValueError,match='unavailable'):
        assemble_pdf(plan,tmp_path/'missing')


@pytest.fixture
def editor(book,store):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from yuzufile.ui import Window
    from yuzufile.organize_ui import OrganizeDialog
    app=QApplication.instance() or QApplication([])
    parent=Window(store);parent.timer.stop()
    dialog=OrganizeDialog(parent,[book])
    yield dialog
    dialog.reject();dialog.deleteLater();parent.deleteLater();app.processEvents()


def select(editor,indices):
    editor.grid.clearSelection()
    for index in indices:
        editor.grid.item(index).setSelected(True)


def test_visual_reorder_rotate_remove_and_undo(editor):
    select(editor,[1,2]);editor.move_selected(-1)
    assert [p['page'] for p in editor.entries()]==[1,2,0,3]
    editor.rotate(90)
    assert [p['rotation'] for p in editor.entries()]==[90,90,0,0]
    editor.remove_selected()
    assert [p['page'] for p in editor.entries()]==[0,3]
    editor.undo()
    assert len(editor.entries())==4
    editor.undo()
    assert all(p['rotation']==0 for p in editor.entries())
    editor.redo()
    assert editor.entries()[0]['rotation']==90


def test_drag_reorder_and_extract_visible_order(editor):
    select(editor,[0,2]);editor.move_to(4)
    assert [p['page'] for p in editor.entries()]==[1,3,0,2]
    select(editor,[0,3]);editor.finish(True)
    assert [p['page'] for p in editor.result_plan['pages']]==[1,2]


def test_removing_every_page_disables_save_and_undo_restores(editor):
    select(editor,range(4));editor.remove_selected()
    assert not editor.save_button.isEnabled()
    editor.undo()
    assert editor.save_button.isEnabled()
    assert len(editor.entries())==4


def test_rotation_preserves_native_text_and_rendering(book,tmp_path):
    plan=plan_for(book,[2,0]);plan['pages'][0]['rotation']=90
    output,_,_=assemble_pdf(plan,tmp_path/'rotated')
    with output,pymupdf.open(book) as original:
        assert output[0].rotation==90
        assert 'Page 3' in output[0].get_text()
        original[2].set_rotation(90)
        assert output[0].get_pixmap().samples==original[2].get_pixmap().samples


@pytest.fixture
def appendix(tmp_path):
    path=tmp_path/'Appendix.pdf'
    with pymupdf.open() as document:
        page=document.new_page(width=500,height=250)
        page.insert_text((40,60),'Appendix material',fontsize=20)
        document.set_toc([[1,'Reference',1]])
        document.save(path)
    return path


def test_merge_interleaved_pages_and_bookmarks(book,appendix,tmp_path):
    originals=[path.read_bytes() for path in (book,appendix)]
    plan={'version':1,'sources':[inspect_source(book),inspect_source(appendix)],
          'pages':[{'source':0,'page':2,'rotation':0}, {'source':1,'page':0,'rotation':90},
                   {'source':0,'page':0,'rotation':0}]}
    output,info,_=assemble_pdf(plan,tmp_path/'merge')
    with output:
        assert [p.get_text().strip() for p in output]==['Page 3','Appendix material','Page 1']
        assert output[1].rect.width==250 and output[1].rect.height==500
        assert info['source_count']==2
        assert any(entry[1:] == ['Reference',2] for entry in output.get_toc())
    assert originals==[path.read_bytes() for path in (book,appendix)]


def test_merge_workspace_add_undo_and_provenance(editor,appendix):
    editor.add_files([appendix])
    assert len(editor.entries())==5
    assert editor.entries()[-1]['source']==1
    assert editor.sources[1]['path']==str(appendix)
    editor.undo();assert len(editor.entries())==4
    editor.redo();assert len(editor.entries())==5


def test_internal_and_external_links_remap_and_excluded_targets_warn(book,tmp_path):
    linked=tmp_path/'linked.pdf'
    with pymupdf.open(book) as document:
        document[0].insert_link({'kind':pymupdf.LINK_GOTO,'from':pymupdf.Rect(30,80,100,100),
                                 'page':3,'to':pymupdf.Point(40,70)})
        document[0].insert_link({'kind':pymupdf.LINK_URI,'from':pymupdf.Rect(30,110,100,130),
                                 'uri':'https://example.com'})
        document.save(linked)
    output,_,warnings=assemble_pdf(plan_for(linked,[3,0]),tmp_path/'linked-output')
    with output,pymupdf.open(stream=output.tobytes(),filetype='pdf') as checked:
        links=checked[1].get_links()
        assert any(link.get('page')==0 for link in links)
        assert any(link.get('uri')=='https://example.com' for link in links)
        assert not warnings
    output,_,warnings=assemble_pdf(plan_for(linked,[0]),tmp_path/'excluded')
    output.close()
    assert any('targeted excluded pages' in warning for warning in warnings)


def test_forms_keep_values_after_merge(tmp_path):
    sources=[]
    for number in range(2):
        path=tmp_path/f'Form-{number}.pdf'
        with pymupdf.open() as document:
            page=document.new_page()
            field=pymupdf.Widget()
            field.field_type=pymupdf.PDF_WIDGET_TYPE_TEXT
            field.field_name='Customer'
            field.field_value=f'Value {number}'
            field.rect=pymupdf.Rect(30,40,200,70)
            page.add_widget(field)
            document.save(path)
        sources.append(inspect_source(path))
    plan={'version':1,'sources':sources,'pages':[{'source':i,'page':0,'rotation':0} for i in range(2)]}
    output,_,_=assemble_pdf(plan,tmp_path/'forms')
    with output,pymupdf.open(stream=output.tobytes(),filetype='pdf') as checked:
        assert [next(page.widgets()).field_value for page in checked]==['Value 0','Value 1']
        assert len({next(page.widgets()).field_name for page in checked})==2


def test_removed_sources_are_not_required(book,appendix,tmp_path):
    plan={'version':1,'sources':[inspect_source(book),inspect_source(appendix)],
          'pages':[{'source':0,'page':0,'rotation':0}]}
    appendix.unlink()
    output,info,_=assemble_pdf(plan,tmp_path/'removed-source')
    with output:
        assert len(output)==1 and info['source_count']==1


def test_add_invalid_file_leaves_workspace_unchanged(editor,tmp_path):
    before=editor.snapshot()
    bad=tmp_path/'broken.pdf';bad.write_bytes(b'not a pdf')
    editor.add_files([bad])
    assert editor.snapshot()==before
    assert editor.message.text()


def test_worker_organizes_into_selected_folder_and_shows_session_result(book,appendix,tmp_path,store):
    import json,time
    from yuzufile.supervisor import Supervisor
    from yuzufile.ui import Window
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    window=Window(store);window.timer.stop()
    destination=tmp_path/'Chosen outputs';destination.mkdir()
    window.set_output_directory(destination)
    window.add_files([str(book),str(appendix)])
    plan={'version':1,'sources':[inspect_source(book),inspect_source(appendix)],
          'pages':[{'source':1,'page':0,'rotation':90},{'source':0,'page':3,'rotation':0}]}
    job=window.enqueue_organization(plan)
    assert not window.pending
    assert json.loads(store.get(job)['page_plan'])['pages'][0]['source']==0
    supervisor=window.supervisor
    deadline=time.monotonic()+60
    try:
        while store.get(job)['state'] in {'queued','running'}:
            supervisor.tick();app.processEvents()
            assert time.monotonic()<deadline
            time.sleep(.03)
        assert store.get(job)['state']=='succeeded',store.get(job)['error']
        result=artifact_path(store.job_dir(job),'pdf')
        assert result.is_relative_to(destination)
        with pymupdf.open(result) as document:
            assert [p.get_text().strip() for p in document]==['Appendix material','Page 4']
            assert document[0].rotation==90
        assert not (result.parent.parent/'staging').exists()
        assert json.loads(store.get(job)['metadata'])['organize']['source_count']==2
        assert window.artifact_path(job,'pdf')==result
        window.session_jobs=[job];window.refresh_queue()
        assert job in window.cards
        assert '+ 1 PDF' in window.job_name(store.get(job))
        opened=[]
        window.open_path=opened.append
        window.open_job_folder(job)
        assert opened==[result.parent]
    finally:
        supervisor.shutdown();window.deleteLater()


def test_organization_history_survives_restart_and_retry_restores_plan(book,tmp_path):
    import json
    from yuzufile.storage import Store
    home=tmp_path/'history'
    value=Store(home)
    plan=plan_for(book,[3,0])
    plan['pages'][0]['rotation']=270
    job=value.create(book,'organize',[],page_plan=plan)
    value.close()
    reopened=Store(home)
    try:
        assert reopened.get(job)['mode']=='organize'
        assert json.loads(reopened.get(job)['page_plan'])==plan
        from PySide6.QtWidgets import QApplication
        from yuzufile.ui import Window
        app=QApplication.instance() or QApplication([])
        window=Window(reopened);window.timer.stop()
        restored=[]
        window.organize_pages=lambda **kwargs:restored.append(kwargs['plan'])
        window.retry_job(job)
        assert restored==[plan]
        window.deleteLater();app.processEvents()
    finally:
        reopened.close()


def test_source_change_after_queue_fails_without_publishing(book,tmp_path,store):
    import time
    from yuzufile.supervisor import Supervisor
    job=store.create(book,'organize',[],page_plan=plan_for(book,[0]))
    book.write_bytes(book.read_bytes()+b'changed after queue')
    supervisor=Supervisor(store);deadline=time.monotonic()+60
    try:
        while store.get(job)['state'] in {'queued','running'}:
            supervisor.tick();assert time.monotonic()<deadline;time.sleep(.03)
        assert store.get(job)['state']=='failed'
        assert 'changed' in store.get(job)['error']
        assert not (store.job_dir(job)/'result').exists()
        assert not (store.job_dir(job)/'staging').exists()
    finally:
        supervisor.shutdown()


def test_thumbnails_only_render_visible_pages(editor,book,tmp_path):
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance()
    extra=tmp_path/'Many pages.pdf'
    with pymupdf.open(book) as source,pymupdf.open() as document:
        for _ in range(12):
            document.insert_pdf(source)
        document.save(extra)
    editor.add_files([extra])
    editor.resize(720,540);editor.show();app.processEvents()
    for _ in range(15):
        editor.timer.stop();editor.render_thumbnail()
    assert 0<len(editor.thumbnail_cache)<editor.grid.count()
    assert len(editor.thumbnail_cache)<=80
    editor.timer.stop()


def test_output_folder_picker_preserves_edits(editor,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    destination=tmp_path/'new output';destination.mkdir()
    select(editor,[2]);editor.rotate(90)
    before=editor.entries()
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *args:str(destination))
    editor.choose_output()
    assert editor.output_directory==destination
    assert editor.entries()==before
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *args:'')
    editor.choose_output()
    assert editor.output_directory==destination


def test_failed_save_keeps_arrangement_available(editor,book):
    select(editor,[1]);editor.rotate(90)
    before=editor.entries()
    book.write_bytes(book.read_bytes()+b'changed')
    editor.finish(False)
    assert editor.result_plan is None
    assert editor.entries()==before
    assert 'changed' in editor.message.text()


def test_drag_drop_callback_moves_rows_exactly_once(editor):
    from PySide6.QtCore import QMimeData,QPointF,Qt
    class Drop:
        def mimeData(self): return QMimeData()
        def source(self): return editor.grid
        def position(self): return QPointF(-1,-1)
        def setDropAction(self,action): assert action==Qt.DropAction.MoveAction
        def accept(self): self.accepted=True
    select(editor,[1,2])
    event=Drop();editor.grid.dropEvent(event)
    assert event.accepted
    assert [page['page'] for page in editor.entries()]==[0,3,1,2]
    assert len(editor.entries())==4
