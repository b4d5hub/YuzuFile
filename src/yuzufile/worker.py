"""One conversion per process; stdout carries structured progress only."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import time

from yuzufile.engines import ConversionError, add_searchable_text, page_needs_ocr, write_markdown
from yuzufile.languages import installed_languages
from yuzufile.operations import MODES
from yuzufile.performance import performance_profile
from yuzufile.resources import library_budget, page_indices
from yuzufile.storage import owned_path, clean_staging


def emit(stage: str, **extra):
    print(json.dumps({"version": 1, "stage": stage, **extra}), flush=True)


def convert(request: dict) -> None:
    try:
        performance = performance_profile(request.get("performance", "balanced"))
    except ValueError as error:
        raise ConversionError(str(error)) from None
    os.environ.update(performance.environment())
    with library_budget(performance):
        _convert(request, performance)


def _convert(request, performance):
    try:
        operations = MODES[request["mode"]]
    except KeyError:
        raise ConversionError("Select a valid combination of operations.") from None
    started = time.monotonic()
    root = Path(request["root"])
    root.mkdir(parents=True, exist_ok=True)
    staging = owned_path(root, "staging")
    if staging.exists() or owned_path(root, "result").exists():
        raise ConversionError("This attempt already has files. Retry to create a new conversion.")
    staging.mkdir()
    document = None
    try:
        emit("Opening PDF", progress=2)
        import pymupdf
        source = Path(request["source"])
        if source.stat().st_size > 1_000_000_000:
            raise ConversionError("The maximum supported PDF size is 1 GB.")
        snapshot = staging / "input.pdf"
        organize_details, organize_warnings = {}, []
        if 'organize' in operations:
            from yuzufile.organize import assemble_pdf
            inputs = staging / 'organize-inputs'
            try:
                document, organize_details, organize_warnings = assemble_pdf(request.get('page_plan'), inputs, performance, emit)
            except ValueError as error:
                raise ConversionError(str(error)) from None
            document.save(snapshot, garbage=3, deflate=True)
            shutil.rmtree(inputs)
        else:
            shutil.copyfile(source, snapshot)
        with snapshot.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if document is None:
            document = pymupdf.open(snapshot)
        if not document.is_pdf:
            raise ConversionError("This file is not a valid PDF.")
        if document.needs_pass:
            raise ConversionError("This PDF is password protected. Save an unlocked copy and try again.")
        count = len(document)
        if not 0 < count <= 2000:
            raise ConversionError("The PDF must contain between 1 and 2,000 pages.")
        if document.get_sigflags() > 0:
            raise ConversionError("This PDF contains signature fields. Convert an unsigned copy to avoid invalidating signatures.")
        emit(f"Checking {count} pages", progress=8)
        scratch = staging / 'scratch'
        scratch.mkdir()
        cleanup_details, cleanup_warnings = {}, []
        if 'cleanup' in operations:
            from yuzufile.cleanup import clean_document
            try:
                cleaned, cleanup_details, cleanup_warnings = clean_document(
                    document, request.get('cleanup_settings'), scratch, performance, emit, source_path=request['source'])
            except ValueError as error:
                raise ConversionError(str(error)) from None
            document.close()
            document = cleaned
        split_details, split_warnings = {}, []
        if 'split' in operations:
            from yuzufile.spreads import split_document
            try:
                divided, split_details, split_warnings = split_document(document, request.get('split_settings'), performance, emit)
            except ValueError as error:
                raise ConversionError(str(error)) from None
            document.close()
            document = divided
            count = len(document)
        # Recognition always starts from visible page pixels. Even a native PDF
        # or an apparently valid old OCR layer must be freshly recognized.
        needs_ocr = bool(operations & {"ocr", "markdown", "docx"})
        languages = request["languages"]
        if needs_ocr:
            available = installed_languages()
            if not languages:
                raise ConversionError("Select at least one language for fresh page recognition.")
            if any(code not in available for code in languages):
                raise ConversionError("A selected OCR language is no longer available. Refresh the language list and try again.")
        statistics = {"ocr_pages": 0, "recognized_pages": 0, "empty_pages": [], "reused_pages": count}
        word_details = {}
        warnings = organize_warnings + cleanup_warnings + split_warnings
        removal_details = {}
        if 'remove_ocr' in operations:
            if needs_ocr:raise ConversionError('Remove OCR is an image-only output. Select recognition tools separately; their old text is cleaned automatically.')
            from yuzufile.ocr_clean import image_only_document
            cleaned,removal_details,extra=image_only_document(document,scratch,emit,performance)
            document.close();document=cleaned;warnings.extend(extra)
            statistics['reused_pages']=0
        if needs_ocr:
            def ocr_notify(stage, **extra):
                extra["progress"] = round(8 + extra.get("progress", 10) / 82 * 54)
                emit(stage, **extra)
            from yuzufile.ocr_clean import DiskBackedDocument,PreparedPageSource,copy_navigation
            prepared=DiskBackedDocument(scratch)
            try:
                if 'docx' in operations:
                    from yuzufile.word_export import write_word
                    statistics={'ocr_pages':0,'recognized_pages':0,'empty_pages':[],'reused_pages':0,
                        'ocr_parts':0,'page_workers':1,'ocr_fallback_pages':[],
                        'indra_pages':[],'indra_fallback_pages':[],'fresh_ocr_pages':[],
                        'arabic_print_pages':[],'ocr_warnings':[],
                        'fresh_ocr':True,'sequential_ocr':True}
                    current_index=[0]
                    def prepare_word_page(index):
                        current_index[0]=index
                        def page_notify(stage,**extra):
                            with contextlib.redirect_stdout(protocol):
                                extra['progress']=round(8+54*(index+min(.8,extra.get('progress',0)/100*.8))/count)
                                emit(stage,**extra)
                        result=add_searchable_text(document,scratch,languages,page_notify,performance,
                            force_ocr=True,sequential=True,target_document=prepared,page_numbers=[index])
                        for key in ('ocr_pages','recognized_pages','ocr_parts'):statistics[key]+=result.get(key,0)
                        for key in ('empty_pages','ocr_fallback_pages','indra_pages','indra_fallback_pages','fresh_ocr_pages','arabic_print_pages','ocr_warnings'):
                            statistics[key].extend(result.get(key,[]))
                    protocol=sys.stdout
                    def page_word_notify(stage,**extra):
                        with contextlib.redirect_stdout(protocol):
                            extra['progress']=round(8+54*(current_index[0]+.9)/count)
                            emit(stage,**extra)
                    # Word appends the current page before asking the preparer
                    # for the next one. No all-document recognition pre-pass.
                    with contextlib.redirect_stdout(sys.stderr):
                        word_details=write_word(PreparedPageSource(prepared,count),staging/'document.docx',
                            page_word_notify,performance,languages,force_visual_ocr=True,prepare_page=prepare_word_page)
                else:
                    statistics = add_searchable_text(document, scratch, languages, ocr_notify, performance,
                        force_ocr=True,sequential=True,target_document=prepared)
                warnings.extend(copy_navigation(document,prepared))
                cleaned=prepared.detach();document.close();document=cleaned
            finally:prepared.close()
            if statistics.get('indra_fallback_pages'):
                warnings.append('Indra could not run on pages ' + ', '.join(map(str, statistics['indra_fallback_pages'])) + '; used existing OCR engines.')
            if statistics.get('ocr_fallback_pages'):
                warnings.append('RapidOCR could not run on pages ' + ', '.join(map(str, statistics['ocr_fallback_pages'])) + '; used bundled Tesseract instead.')
        else:
            emit("Preparing outputs", progress=62)
        native_image_pages = [number for number in statistics['empty_pages'] if document[number-1].get_text().strip()]
        warnings.extend(statistics.get('ocr_warnings', []))
        unrecognized_pages = [number for number in statistics['empty_pages'] if number not in native_image_pages]
        if unrecognized_pages:
            pages = ", ".join(map(str, unrecognized_pages))
            warnings.append(f"No text recognized on pages {pages}. They may contain only pictures, be blank, or need a clearer scan or different language.")
        elif operations & {"ocr", "markdown", "docx"} and not any(page.get_text().strip() for page in document):
            warnings.append("No text was found. This PDF may contain only blank pages or pictures.")
        artifacts = []
        if 'remove_ocr' in operations and 'compress' not in operations:
            from yuzufile.ocr_clean import validate_image_only
            result=staging/'document.no-ocr.pdf'
            document.save(result,garbage=4,deflate=True)
            with pymupdf.open(result) as verified:
                if len(verified)!=count:raise ConversionError('Image-only output page count did not match the source.')
                validate_image_only(verified)
            artifacts.append({'path':'result/document.no-ocr.pdf','kind':'pdf'})
        if 'cleanup' in operations and not operations & {'ocr','compress','split','remove_ocr'}:
            emit('Saving cleaned PDF', progress=64)
            document.save(staging / 'document.cleaned.pdf',garbage=3,deflate=True)
            with pymupdf.open(staging / 'document.cleaned.pdf') as verified:
                if len(verified) != count:
                    raise ConversionError('Cleaned PDF validation found a page-count mismatch.')
            artifacts.append({'path':'result/document.cleaned.pdf','kind':'pdf'})
        if 'organize' in operations:
            emit('Saving organized PDF', progress=75)
            result = staging / 'document.organized.pdf'
            document.save(result, garbage=3, deflate=True)
            with pymupdf.open(result) as verified:
                if len(verified) != count:
                    raise ConversionError('Organized PDF page count did not match the arrangement.')
            artifacts.append({'path':'result/document.organized.pdf','kind':'pdf'})
        if 'split' in operations and not operations & {'ocr', 'compress','remove_ocr'}:
            document.save(staging / 'document.split.pdf', garbage=3, deflate=True)
            artifacts.append({'path': 'result/document.split.pdf', 'kind': 'pdf'})
        if "ocr" in operations and "compress" not in operations:
            emit("Saving searchable PDF", progress=64)
            result = staging / "document.ocr.pdf"
            document.save(result, garbage=4, deflate=True)
            with pymupdf.open(result) as verified:
                if len(verified) != count:
                    raise ConversionError("Output validation found a page-count mismatch.")
                for index in page_indices(count, performance, emit, "Checking searchable PDF", 64, 65):
                    page = document[index]
                    if page.get_text().strip() and not verified[index].get_text().strip():
                        raise ConversionError(f"Output validation found missing text on page {index + 1}.")
            artifacts.append({"path": "result/document.ocr.pdf", "kind": "pdf"})
        if "markdown" in operations:
            emit("Preparing Markdown", progress=65)
            protocol = sys.stdout
            with contextlib.redirect_stdout(sys.stderr):
                def notify(stage, **extra):
                    with contextlib.redirect_stdout(protocol):
                        extra["progress"] = round(65 + (extra.get("progress", 83) - 83) / 12 * 17)
                        emit(stage, **extra)
                warnings += write_markdown(document, staging / "document.md", notify, performance, languages, native_image_pages,fresh_ocr=True)
            artifacts.append({"path": "result/document.md", "kind": "markdown"})
            for asset in (staging / "assets").glob("*"):
                artifacts.append({"path": "result/assets/" + asset.name, "kind": "asset"})
        if 'docx' in operations:
            warnings.extend(word_details['warnings'])
            artifacts.extend([{'path':'result/document.docx','kind':'docx'},
                              {'path':'result/document.quality.json','kind':'report'}])
        compression_details = {}
        if "compress" in operations:
            from yuzufile.compression import compress_pdf
            # If OCR added text, fallback must preserve it even when image savings
            # cannot offset the text-layer size. Never fall back to the scanned input.
            fallback = snapshot
            if statistics["ocr_pages"] or operations & {'split','cleanup','remove_ocr'}:
                fallback = scratch / "searchable.pdf"
                document.save(fallback, garbage=0, deflate=False)
            def compression_notify(stage, **extra):
                start = 90 if 'docx' in operations else 83
                extra["progress"] = round(start + extra.get("progress", 0) / 100 * (97-start))
                emit(stage, **extra)
            compression_details = compress_pdf(document, fallback, staging / "document.compressed.pdf",
                                               request.get("compression", "balanced"), compression_notify, performance)
            warnings.extend(compression_details.pop("warnings"))
            compression_details["input_bytes"] = snapshot.stat().st_size
            compression_details["saved_percent"] = round(
                (1 - compression_details["output_bytes"] / compression_details["input_bytes"]) * 100, 2)
            if compression_details["output_bytes"] > compression_details["input_bytes"]:
                if 'remove_ocr' in operations:
                    warnings.append('Image-only rendering made this PDF larger than the original. Compression could not offset the added image size.')
                elif needs_ocr:
                    warnings.append('Fresh page images and searchable text made this PDF larger than the original. Compression could not offset the added size.')
                else:
                    warnings.append('This processed PDF is larger than the original. Page processing can change the file size.')
            artifacts.append({"path": "result/document.compressed.pdf", "kind": "pdf"})
            if 'remove_ocr' in operations:
                from yuzufile.ocr_clean import validate_image_only
                with pymupdf.open(staging/'document.compressed.pdf') as verified:validate_image_only(verified)
        document.close()
        document = None
        snapshot.unlink()
        used_file = scratch / 'markdown-engines.json'
        markdown_engines = json.loads(used_file.read_text(encoding='utf-8')) if used_file.exists() else ['pymupdf4llm'] if 'markdown' in operations else []
        indra_used = bool(statistics.get('indra_pages')) or 'indra-ocr-1.1.2' in markdown_engines or 'indra-ocr-1.1.2' in word_details.get('engines_used', [])
        if indra_used:
            from yuzufile.indra_engine import output_license
            output_license(staging)
            for name in ('INDRA-MODEL-LICENSE.txt', 'INDRA-NOTICE.txt'):
                artifacts.append({'path': 'result/' + name, 'kind': 'license'})
        shutil.rmtree(scratch)
        metadata = {"pages": count, "sha256": digest, "seconds": round(time.monotonic() - started, 2),
            "warnings": warnings, "operations": sorted(operations), **statistics, **compression_details,
            "engines": {name: importlib.metadata.version(name) for name in ("PyMuPDF", "pymupdf4llm")},
            "performance": performance.code,
            "resource_limits": {"cpu_percent": performance.cpu_percent, "memory_mb": performance.memory_mb,
                                "page_workers": performance.page_workers(), "max_pixels_per_page": 8_000_000},
            "library_resources": {"cache_clear_every_pages": performance.page_workers(),
                                  "low_memory_rendering": performance.code == "low"},
            "ocr_engine": "RapidOCR 3.10 / PP-OCRv6 + Arabic PP-OCRv5" if __import__('yuzufile.neural_text', fromlist=['available']).available() and set(languages) <= {'eng','fra','ara'} else "Tesseract 5 / bounded page OCR", "ocr_dpi": 300}
        from yuzufile.vision_runtime import available as vision_available
        metadata['markdown_engines_used'] = markdown_engines
        if word_details:
            metadata['word'] = word_details
            metadata['engines']['python-docx'] = importlib.metadata.version('python-docx')
        if indra_used:
            from yuzufile.indra_engine import ENGINE
            metadata['personal_use_build'] = True
            metadata['indra_model_revision'] = 'bd02167fdf2005a19962cc15188f8496a2c87d3b'
            metadata['engines']['indra-ocr'] = importlib.metadata.version('indra-ocr')
            if statistics.get('indra_pages'):
                metadata['ocr_engine'] = ENGINE
        if statistics.get('arabic_print_pages'):
            from yuzufile.arabic_ocr import ENGINE as print_engine
            metadata['ocr_engine'] += ' + ' + print_engine
        if split_details:
            metadata['split'] = split_details
        if cleanup_details:
            metadata['cleanup'] = cleanup_details
        if organize_details:
            metadata['organize'] = organize_details
        if removal_details:metadata['remove_ocr']=removal_details
        if needs_ocr or 'remove_ocr' in operations:
            metadata['library_resources']['cache_clear_every_pages']=1
            metadata['resource_limits']['page_workers']=1
            metadata['text_preparation']={'method':'visible-page-raster','old_text_reused':False,
                'pages':count,'page_workers':1,'max_pixels_per_page':8_000_000,'target_dpi':300}
        if needs_ocr:
            metadata['ocr_pipeline']='Page by page: image-only cleanup, fresh recognition, export'
        if 'remove_ocr' in operations:
            metadata['ocr_engine']='Not run; image-only PDF with no searchable text'
        elif not statistics['ocr_pages']:
            metadata['ocr_engine'] = 'Existing PDF text reused; no new searchable-PDF OCR'
        if statistics.get('ocr_fallback_pages'):
            metadata['ocr_engine'] += ' / Tesseract fallback on recorded pages'
        if vision_available() and 'markdown' in operations:
            metadata['markdown_pipeline'] = 'Native text when available; visual pages: LightOnOCR-3 + PP-DocLayoutV3 + selective PaddleOCR-VL-1.6 verification + RapidOCR coverage recovery'
            metadata['engines'].update({name: importlib.metadata.version(name) for name in ('rapidocr', 'rapid-layout', 'onnxruntime')})
        if 'indra-ocr-1.1.2' in markdown_engines:
            metadata['markdown_pipeline'] = 'Indra CPU OCR/layout/tables; native text preservation; existing engines on failed pages'
        if needs_ocr and 'markdown' in operations:
            metadata['markdown_pipeline']='Fresh page OCR/layout/tables after image-only cleanup; old PDF text is never reused'
        from yuzufile.output_names import rename_outputs
        naming_operations={'merge'} if operations=={'organize'} and request.get('page_plan',{}).get('action')=='merge' else operations
        artifacts=rename_outputs(staging,source,naming_operations,artifacts)
        (staging / "manifest.json").write_text(json.dumps({"artifacts": artifacts, "metadata": metadata}), encoding="utf-8")
        emit("Checking output files", progress=98)
        staging.rename(owned_path(root, "result"))
        emit("Completed", progress=100)
    finally:
        if document is not None:
            document.close()
        if staging.exists():
            try:
                clean_staging(root)
            except OSError:
                pass


def main() -> int:
    from yuzufile.native_process import hide_helper_windows
    hide_helper_windows()
    logging.disable(logging.CRITICAL)
    try:
        request = json.loads(sys.stdin.readline())
        convert(request)
        return 0
    except Exception as error:
        name = type(error).__name__
        messages = {
            "FileDataError": "This PDF is damaged or unreadable. Try exporting a new copy from your PDF viewer.",
            "EmptyFileError": "This PDF is empty.",
            "PermissionError": "A file is locked or its folder is not writable. Close the output file and retry.",
            "FileNotFoundError": "The source file or OCR engine could not be found.",
            "ModuleNotFoundError": "A required app component is missing. Extract the complete application ZIP and retry.",
            "MemoryError": "This PDF exceeded the available memory budget. Try a higher performance level, close other applications, or split the PDF.",
        }
        message = str(error) if isinstance(error, ConversionError) or isinstance(error,RuntimeError) and str(error).startswith('Word page ') else messages.get(name,
            f"Conversion stopped ({name}). The source is unchanged; retry or export a fresh PDF copy.")
        if isinstance(error, OSError) and error.errno == 28:
            message = "The destination disk is full. Free some space and retry."
        emit("Failed", error=message, error_code=name)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
