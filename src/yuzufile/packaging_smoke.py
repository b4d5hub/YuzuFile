"""Internal frozen-build smoke check; normal users launch the GUI directly."""
import json
import sys
import time
from pathlib import Path


def main():
    from PySide6.QtWidgets import QApplication
    from yuzufile.languages import installed_languages, tesseract_executable
    from yuzufile.storage import Store
    from yuzufile.ui import Window

    report = Path(sys.argv[sys.argv.index("--smoke-ui-report") + 1])
    app = QApplication([sys.argv[0]])
    app.setStyle('Fusion')
    from PySide6.QtGui import QFontDatabase
    for filename in ('segoeui.ttf','seguisb.ttf','segoeuib.ttf'):
        font = Path('C:/Windows/Fonts') / filename
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    store = Store(report.parent / "smoke-library")
    view = Window(store)
    view.timer.stop()
    shell = None
    resident_shell = '--smoke-resident-shell' in sys.argv
    if '--smoke-shaped-shell' in sys.argv:
        from yuzufile.shaped_shell import FloatingShell
        shell=FloatingShell(view)
        if resident_shell:
            # Layout/workflow smoke runs offscreen, where the OS tray is absent.
            # Native tray registration/startup are verified separately on Windows.
            class ResidentHost:
                active=True
                def hide_window(self):shell.hide();return True
            shell.tray_controller=ResidentHost();shell.enter_resident_mode()
        else:shell.show()
    else:view.show()
    app.processEvents()
    if shell is not None:
        from PySide6.QtCore import Qt,QPoint
        assert shell.windowFlags() & Qt.WindowType.FramelessWindowHint
        if resident_shell:
            assert shell.mode=='idle' and not shell.isVisible() and not shell.wheel.isVisible()
        else:
            assert not shell.mask().contains(QPoint(0,0))
            assert shell.mask().contains(shell.wheel.mapTo(shell,shell.wheel.rect().center()))
            shell.grab().save(str(report.with_name(report.stem+'-wheel.png')))
    job_state = None
    if "--smoke-source" in sys.argv:
        source = Path(sys.argv[sys.argv.index("--smoke-source") + 1])
        view.add_files([str(source)])
        view.operations["markdown"].setChecked(True)
        view.operations["compress"].setChecked(True)
        if '--smoke-word' in sys.argv:
            view.operations['docx'].setChecked(True)
        if '--smoke-word-only' in sys.argv:
            for code,card in view.operations.items():
                card.setChecked(code=='docx')
        if '--smoke-fresh-combined' in sys.argv:
            for code,card in view.operations.items():card.setChecked(code in {'ocr','markdown','docx'})
        if '--smoke-ocr-only' in sys.argv:
            for code,card in view.operations.items():card.setChecked(code=='ocr')
        if '--smoke-compress-only' in sys.argv:
            for code,card in view.operations.items():card.setChecked(code=='compress')
        if '--smoke-markdown-only' in sys.argv:
            for code,card in view.operations.items():card.setChecked(code=='markdown')
        if '--smoke-remove-ocr' in sys.argv:
            for code,card in view.operations.items():card.setChecked(code=='remove_ocr')
            if '--smoke-remove-compress' in sys.argv:
                view.operations['compress'].setChecked(True)
                view.compression.setCurrentIndex(view.compression.findData('lossless'))
        if '--smoke-languages' in sys.argv:
            chosen=sys.argv[sys.argv.index('--smoke-languages')+1].split(',')
            for code,box in view.languages.items():box.setChecked(code in chosen)
        if '--smoke-cleanup' in sys.argv or '--smoke-cleanup-only' in sys.argv:
            if '--smoke-cleanup-only' in sys.argv:
                for code,card in view.operations.items():card.setChecked(code=='cleanup')
            else:
                view.operations['cleanup'].setChecked(True)
            from yuzufile.cleanup_preview import CleanupPreview
            from yuzufile.ui import CompressionBox
            preview=CleanupPreview(view,[source],view.current_cleanup_settings(),CompressionBox)
            preview.show();app.processEvents()
            assert preview.apply.isEnabled()
            assert preview.edit_view.width()>preview.width()*.9
            preview.edit_view.set_zoom(1.5);preview.render_raster()
            before_crop=preview.before.crop[:]
            preview.show_view(1);preview.render_raster();app.processEvents()
            assert preview.result_view.isVisible() and not preview.edit_view.isVisible()
            assert preview.before.crop==before_crop
            preview.show_view(0)
            if '--smoke-visual-edits' in sys.argv:
                preview.begin_edit();preview.crop_live([.1,.1,.9,.9]);preview.finish_edit()
                preview.set_edit(angle=3.0,rotation=90);preview.render_page()
                assert preview.apply.isEnabled() and preview.detail['manual_crop']
                view.cleanup_visual=preview.config()['visual']
            preview.grab().save(str(report.with_name(report.stem+'-cleanup.png')))
            preview.reject();preview.deleteLater()
        if '--smoke-split-order' in sys.argv:
            order = sys.argv[sys.argv.index('--smoke-split-order')+1]
            view.operations['split'].setChecked(True)
            view.split_direction.setCurrentIndex(view.split_direction.findData(order))
        if '--smoke-split-parts' in sys.argv:
            view.split_parts.setValue(int(sys.argv[sys.argv.index('--smoke-split-parts')+1]))
            if '--smoke-visual-edits' in sys.argv and view.split_parts.value()==3:
                view.split_cuts=[20,70]
        if '--smoke-spread-editor' in sys.argv:
            from yuzufile.spread_preview import SpreadPreview
            from yuzufile.ui import CompressionBox
            from PySide6.QtCore import QPointF
            preview=SpreadPreview(view,[source],view.current_split_settings(),CompressionBox)
            preview.show()
            for _ in range(4):app.processEvents()
            assert preview.viewport.mode=='width'
            assert abs(preview.canvas.fit_rect().width()-preview.viewport.viewport().width()+48)<3
            preview.viewport.set_zoom(preview.viewport.zoom*1.5);preview.render_raster()
            preview.cut_selector.setCurrentIndex(preview.cut_selector.count()-1)
            preview.cut_position.setValue(preview.cut_position.value()-1)
            cuts=list(preview.canvas.cuts())
            preview.viewport.pan_by(QPointF(0,-60))
            assert preview.canvas.cuts()==cuts
            assert preview.raster_size[0]*preview.raster_size[1]<=8_020_000
            preview.grab().save(str(report.with_name(report.stem+'-spread-editor.png')))
            config=preview.config();view.split_cuts=config['cuts']
            view.split_position.setValue(config['position'])
            preview.reject();assert not preview.raster_timer.isActive()
            preview.deleteLater()
        view.performance.setCurrentIndex(view.performance.findData("low"))
        if "--smoke-output-directory" in sys.argv:
            destination = Path(sys.argv[sys.argv.index("--smoke-output-directory") + 1])
            view.set_output_directory(destination)
        if shell is not None:
            shell.show_tray()
            if resident_shell:shell.showNormal()
            app.processEvents()
            assert not view.isVisible() and view.start_button.isVisible()
            assert shell.output_directory==view.output_directory
            assert shell.form_scroll.horizontalScrollBar().maximum()==0
            shell.grab().save(str(report.with_name(report.stem+'-tray.png')))
        if '--smoke-merge' in sys.argv:
            from yuzufile.merge_ui import MergeDialog
            other=Path(sys.argv[sys.argv.index('--smoke-add-pdf')+1])
            dialog=MergeDialog(view,[source,other]);dialog.show();app.processEvents()
            assert dialog.documents.count()==2 and dialog.merge_button.isEnabled()
            dialog.move_document(1,-1);dialog.grab().save(str(report.with_name(report.stem+'-merge.png')))
            dialog.finish();assert dialog.result_plan['action']=='merge'
            view.enqueue_organization(dialog.result_plan);dialog.deleteLater()
        elif '--smoke-organize' in sys.argv:
            from yuzufile.organize_ui import OrganizeDialog
            paths=[source]
            if '--smoke-add-pdf' in sys.argv:
                paths.append(Path(sys.argv[sys.argv.index('--smoke-add-pdf')+1]))
            dialog=OrganizeDialog(view,paths)
            dialog.show();app.processEvents()
            dialog.grid.item(dialog.grid.count()-1).setSelected(True)
            dialog.move_to(0)
            assert dialog.grid.landed=={0} and 'Moved' in dialog.message.text()
            dialog.rotate(90)
            plan_before=dialog.entries();dialog.page_size.setValue(250);app.processEvents()
            assert dialog.entries()==plan_before and dialog.grid.iconSize().width()==250
            from yuzufile.page_preview import PagePreview
            reader=PagePreview(dialog,dialog.sources,dialog.entries(),0)
            reader.show();app.processEvents();reader.view.set_zoom(2);reader.render()
            assert reader.pdf_page.rotation==90
            assert reader.canvas.pixmap.width()*reader.canvas.pixmap.height()<=8_020_000
            reader.grab().save(str(report.with_name(report.stem+'-page-reader.png')))
            reader.reject();assert reader.document is None and not reader.timer.isActive()
            reader.deleteLater()
            dialog.grid.clearSelection()
            dialog.grid.item(0).setSelected(True)
            dialog.grid.item(2).setSelected(True)
            for _ in range(12):
                dialog.timer.stop();dialog.render_thumbnail();app.processEvents()
            card=dialog.grid.visualItemRect(dialog.grid.item(0))
            page_rect=dialog.grid.itemDelegate().image_rect(card,dialog.grid.model().index(0,0))
            assert abs(page_rect.width()-dialog.page_size.value())<3
            assert page_rect.height()>card.height()*.7
            dialog.grid.dragging=True;dialog.grid.dragged_rows=[0,2];dialog.grid.target=1
            dialog.grab().save(str(report.with_name(report.stem+'-organizer.png')))
            dialog.grid.dragging=False;dialog.grid.target=None
            dialog.finish(True)
            assert dialog.result_plan
            view.enqueue_organization(dialog.result_plan)
            dialog.deleteLater()
        else:
            view.enqueue()
        job_id = store.jobs()[0]["id"]
        capsule_position = None
        if shell is not None:
            shell.sync_from_controller();app.processEvents()
            shell.move(QPoint(35,45));app.processEvents();capsule_position=shell.pos()
        assert store.get(job_id)["performance"] == "low"
        if '--smoke-split-order' in sys.argv:
            assert json.loads(store.get(job_id)['split_settings'])['direction'] == order
        if '--smoke-split-parts' in sys.argv:
            assert json.loads(store.get(job_id)['split_settings'])['parts'] == view.split_parts.value()
        if "--smoke-output-directory" in sys.argv:
            assert store.job_dir(job_id).parent == destination.resolve()
        assert view.performance.currentData() == "balanced"
        deadline = time.monotonic() + 300
        while store.get(job_id)["state"] in {"queued", "running"}:
            view.poll()
            app.processEvents()
            if time.monotonic() > deadline:
                view.supervisor.shutdown()
                raise TimeoutError("Frozen GUI conversion timed out")
            time.sleep(0.05)
        job_state = store.get(job_id)["state"]
        assert json.loads(store.get(job_id)["metadata"])["performance"] == "low"
        assert json.loads(store.get(job_id)["metadata"])["library_resources"] == {
            "cache_clear_every_pages": 1, "low_memory_rendering": True}
        view.poll()
        app.processEvents()
    if shell is not None:
        shell.sync_from_controller();app.processEvents()
        assert shell.mode=='progress' and not shell.mask().contains(QPoint(0,0))
        assert shell.pos()==capsule_position,'Completion moved the processing window'
        assert shell.pill_tools.isVisible() and shell.pill_tools.text()==('Done' if resident_shell else 'Back to tools')
        assert shell.pill_tools.height()>=32
        shell.pill_tools.click();app.processEvents()
        if resident_shell:
            assert not shell.isVisible() and not shell.wheel.isVisible()
            assert shell.show_current()
        else:
            assert shell.mode=='wheel' and shell.wheel.isVisible()
            shell.files_button.click()
        app.processEvents()
        assert shell.mode=='progress' and shell.result_actions.isVisible()
        assert all(button.height()>=32 for button in shell.result_actions.findChildren(type(shell.pill_tools)))
        shell.grab().save(str(report.with_suffix('.png')))
    else:view.grab().save(str(report.with_suffix(".png")))
    result_actions = []
    if job_state:
        menu = view.create_job_menu(job_id)
        result_actions = [a.text() for a in menu.actions() if a.isEnabled() and not a.isSeparator()]
        view.tabs.setCurrentIndex(0)
        view.clear_finished()
        assert store.get(job_id)["state"] == "succeeded"
        from yuzufile.operations import MODES
        selected=MODES[store.get(job_id)['mode']]
        from yuzufile.output_names import output_name
        naming_selected={'merge'} if json.loads(store.get(job_id)['page_plan']).get('action')=='merge' else selected
        for artifact in store.artifacts(job_id):
            if artifact['kind'] in {'pdf','markdown','docx','report'}:
                assert Path(artifact['path']).name==output_name(Path(store.get(job_id)['source']),naming_selected,artifact['kind'])
        expected=int('markdown' in selected)+int('docx' in selected)+int(bool(selected & {'ocr','compress','split','cleanup','organize','remove_ocr'}))
        assert len([a for a in store.artifacts(job_id) if a['kind'] in {'pdf', 'markdown', 'docx'}]) == expected
        if 'remove_ocr' in selected:
            import pymupdf
            from yuzufile.ocr_clean import validate_image_only
            with pymupdf.open(view.artifact_path(job_id,'pdf')) as image_only:validate_image_only(image_only)
        if selected & {'ocr','markdown','docx'}:
            meta=json.loads(store.get(job_id)['metadata'])
            assert meta['text_preparation']['old_text_reused'] is False
            assert meta['reused_pages']==0 and meta['ocr_pages']==meta['pages']
            if 'docx' in selected:assert meta['word']['fresh_ocr_pages']==meta['pages']
    report.write_text(json.dumps({"title": view.windowTitle(), "tabs": view.tabs.count(),
        'shaped_shell':shell is not None,'shell_mode':shell.mode if shell is not None else None,
        'resident_shell':resident_shell,
        'text_preparation':json.loads(store.get(job_id)['metadata']).get('text_preparation') if job_state else None,
        'remove_ocr':json.loads(store.get(job_id)['metadata']).get('remove_ocr') if job_state else None,
        "languages": installed_languages(), "tesseract": tesseract_executable(),
        "frozen": getattr(sys, "frozen", False), "job_state": job_state,
        "job_mode": store.get(job_id)['mode'] if job_state else None,
        "operations": sorted(view.selected_operations()), "home_active": view.home_link.isChecked(),
        "performance": view.performance.currentData(),
        "output_directory": str(view.output_directory) if view.output_directory else None,
        "split": json.loads(store.get(job_id)['metadata']).get('split') if job_state else None,
        "organize": json.loads(store.get(job_id)['metadata']).get('organize') if job_state else None,
        'cleanup': json.loads(store.get(job_id)['metadata']).get('cleanup') if job_state else None,
        'word': json.loads(store.get(job_id)['metadata']).get('word') if job_state else None,
        "result_actions": result_actions,
        "result_count": len([a for a in store.artifacts(job_id) if a["kind"] in {"pdf", "markdown", "docx"}])
            if job_state else 0}, indent=2), encoding="utf-8")
    if shell is not None:shell.request_quit();shell.deleteLater()
    else:store.close()
    view.deleteLater()
    app.processEvents()
    return 0
