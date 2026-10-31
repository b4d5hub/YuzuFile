"""Verify the packaged app with no Python/Tesseract locations on PATH."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import unicodedata


def artifact(root,kind):
    manifest=json.loads((root/'result/manifest.json').read_text(encoding='utf-8'))
    matches=[root/item['path'] for item in manifest['artifacts'] if item['kind']==kind]
    assert len(matches)==1 and matches[0].is_file(),(kind,manifest['artifacts'])
    return matches[0]


def assert_visually_equivalent(before,after):
    from PIL import Image,ImageChops,ImageStat
    assert (before.width,before.height)==(after.width,after.height)
    images=[Image.frombytes('RGB',(pix.width,pix.height),pix.samples) for pix in (before,after)]
    assert max(ImageStat.Stat(ImageChops.difference(*images)).mean)<3


def main():
    from yuzufile import __version__
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, default=Path('dist')/f'yuzufile-{__version__}')
    parser.add_argument('--require-neural', action='store_true', help='Fail if visual models fall back; needs free model memory')
    parser.add_argument("--output", type=Path, default=Path("tmp/frozen-smoke"))
    args = parser.parse_args()
    folder = args.app.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    for key in list(environment):
        if key.upper().startswith(("PYTHON", "TESSDATA", "VIRTUAL_ENV")):
            environment.pop(key)
    environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment['HTTP_PROXY'] = 'http://127.0.0.1:9'
    environment['HTTPS_PROXY'] = 'http://127.0.0.1:9'
    environment['HF_HUB_OFFLINE'] = '1'
    # An invalid inherited setting must not override bundled language data.
    environment["TESSDATA_PREFIX"] = str(output / "not-installed")
    worker = folder / "yuzufile-worker.exe"
    result = subprocess.run([str(worker), "doctor"], env=environment, cwd=output,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    doctor = json.loads(result.stdout)
    assert "eng" in doctor["languages"]
    assert str(folder) in doctor["tesseract"]
    (output / "doctor.json").write_text(result.stdout, encoding="utf-8")

    import pymupdf
    digital = output / "source with spaces.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 90), "Packaged PDF conversion", fontsize=24)
        page.insert_text((72, 140), "Hello world. Offline OCR works.", fontsize=14)
        doc.save(digital)
    scanned = output / "scanned.pdf"
    with pymupdf.open(digital) as source, pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_image(page.rect, pixmap=source[0].get_pixmap(dpi=200))
        doc.save(scanned)

    for mode, source, languages in (("markdown", digital, ["eng"]), ("both", scanned, ["eng"])):
        root = output / ("job-" + mode)
        request = {"root": str(root), "source": str(source), "mode": mode, "languages": languages}
        result = subprocess.run([str(worker), "--worker"], input=json.dumps(request) + "\n",
            env=environment, cwd=output, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Hello world" in artifact(root,'markdown').read_text(encoding="utf-8")
        manifest = json.loads((root / "result/manifest.json").read_text(encoding="utf-8"))
        if args.require_neural and mode == 'both':
            engines=manifest['metadata'].get('markdown_engines_used', [])
            assert any(engine=='lighton' or engine.startswith('indra-ocr-') for engine in engines),manifest['metadata']['warnings']
            assert not manifest['metadata'].get('indra_fallback_pages') and not manifest['metadata'].get('ocr_fallback_pages')
        if mode == "both":
            with pymupdf.open(artifact(root,'pdf')) as doc:
                assert "Hello world" in doc[0].get_text()
                doc[0].get_pixmap(dpi=90).save(output / "ocr-output.png")

    # Existing searchable OCR plus a large vector rectangle reproduced a silent
    # empty-text result in the old layout converter. It is freshly recognized.
    searchable = output / "already-searchable-with-graphics.pdf"
    with pymupdf.open(artifact(output/'job-both','pdf')) as doc:
        doc[0].draw_rect(doc[0].rect, color=(0.8, 0.8, 0.8), overlay=False)
        doc.save(searchable)
    root = output / "job-existing-ocr"
    request = {"root": str(root), "source": str(searchable), "mode": "markdown", "languages": ['eng']}
    result = subprocess.run([str(worker), "--worker"], input=json.dumps(request) + "\n",
        env=environment, cwd=output, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Hello world" in artifact(root,'markdown').read_text(encoding="utf-8")
    metadata = json.loads((root / "result/manifest.json").read_text(encoding="utf-8"))["metadata"]
    assert metadata['ocr_pages']==1 and metadata['reused_pages']==0
    assert metadata['text_preparation']['old_text_reused'] is False

    # Verify the actual frozen Arabic recognizer, helper pipe encoding and
    # searchable text order; ASCII-only smoke input cannot catch these bugs.
    mixed = output / 'mixed-scanned.pdf'
    with pymupdf.open() as text_doc, pymupdf.open() as scan_doc:
        page=text_doc.new_page(width=650,height=350)
        page.insert_htmlbox(pymupdf.Rect(40,30,610,310),
            '<p>Hello world</p><p>Bonjour, sécurité française.</p><p dir="rtl">مرحبا بالعالم</p>',
            css='body {font-family: sans-serif; font-size: 28pt;} p {margin: 12pt 0;}')
        scan=scan_doc.new_page(width=650,height=350)
        scan.insert_image(scan.rect,pixmap=page.get_pixmap(matrix=pymupdf.Matrix(2,2),alpha=False))
        before=scan.get_pixmap(dpi=72)
        scan_doc.save(mixed)
    root=output/'job-mixed'
    request={'root':str(root),'source':str(mixed),'mode':'pdf','languages':['eng','fra','ara']}
    result=subprocess.run([str(worker),'--worker'],input=json.dumps(request)+'\n',env=environment,cwd=output,
        capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
    with pymupdf.open(artifact(root,'pdf')) as doc:
        text=unicodedata.normalize('NFKC',doc[0].get_text())
        assert all(value in text for value in ['Hello world','française','مرحبا']),text
        assert_visually_equivalent(before,doc[0].get_pixmap(dpi=72))

    for level in ("lossless", "balanced", "maximum"):
        root = output / ("compress-" + level)
        request = {"root": str(root), "source": str(scanned), "mode": "compress",
                   "languages": [], "compression": level}
        result = subprocess.run([str(worker), "--worker"], input=json.dumps(request) + "\n",
            env=environment, cwd=output, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
        metadata = json.loads((root / "result/manifest.json").read_text(encoding="utf-8"))["metadata"]
        assert metadata["output_bytes"] <= metadata["input_bytes"]
        with pymupdf.open(artifact(root,'pdf')) as doc:
            assert len(doc) == 1
            assert len(doc[0].get_pixmap().samples) > 0

    report = output / "gui.json"
    desktop = subprocess.run([str(folder / "yuzufile.exe"), "--smoke-ui-report", str(report), "--smoke-source", str(scanned)],
        env=environment, cwd=output, capture_output=True, timeout=330)
    assert desktop.returncode == 0, desktop.stderr
    ui = json.loads(report.read_text(encoding="utf-8"))
    assert ui["frozen"] and ui["tabs"] == 2 and "eng" in ui["languages"]
    assert ui["job_state"] == "succeeded", ui
    assert ui["home_active"] and ui["operations"] == ["compress", "markdown", "ocr"], ui
    assert ui["result_count"] == 2, ui
    assert ui["history_rows"] >= 1, ui
    assert {"Open PDF", "Open Markdown", "Open Folder", "View Details"} <= set(ui["history_actions"]), ui
    print("Packaged GUI, bundled-language discovery, Markdown, scanned OCR and all three compression levels passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
