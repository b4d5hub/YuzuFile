# Build with: .venv/Scripts/python.exe -m PyInstaller packaging/YuzuFile.spec
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

project = Path(SPECPATH).parent
sys.path.insert(0, str(project / "src"))
from yuzufile.languages import tesseract_executable
from yuzufile import __version__

tesseract = Path(os.environ.get("YUZUFILE_TESSERACT", "") or os.environ.get("PDFAI_TESSERACT", "") or tesseract_executable() or "missing")
if not tesseract.is_file():
    raise RuntimeError("Install Tesseract or set YUZUFILE_TESSERACT to tesseract.exe before building.")

datas = []
binaries = []
hiddenimports = ["yuzufile.ui", "yuzufile.cli", "yuzufile.worker"]
for package in ("pymupdf", "pymupdf4llm", "rapidocr", "rapid_layout", "indra_ocr", "pypdfium2", "docx"):
    package_data, package_binaries, package_imports = collect_all(package)
    datas += [(source, target) for source, target in package_data
              if "/layout/" not in source.replace("\\", "/")]
    binaries += package_binaries
    hiddenimports += [name for name in package_imports if not name.startswith("pymupdf.layout")]
for name in ("PyMuPDF", "pymupdf4llm", "PySide6-Essentials", "Pillow", "rapidocr", "rapid-layout", "onnxruntime", "indra-ocr", "pypdfium2", "python-docx"):
    datas += copy_metadata(name)

neural = project / 'vendor/neural'
datas.append((str(neural / 'indra'), 'neural/indra'))
datas.append((str(neural / 'arabic-print'), 'neural/arabic-print'))
for folder in ('paddle', 'lighton', 'layout'):
    for file in (neural / folder).iterdir():
        if file.suffix in {'.gguf', '.onnx'}:
            datas.append((str(file), 'neural/' + folder))
for name in ('PP-OCRv6_det_small.onnx', 'PP-OCRv6_rec_medium.onnx', 'arabic_PP-OCRv5_rec_mobile.onnx', 'ready.json'):
    datas.append((str(neural / 'rapid' / name), 'neural/rapid'))
for file in (neural / 'runtime').iterdir():
    if file.suffix == '.dll' or file.name in {'llama-server.exe', 'LICENSE-LLVM-OpenMP'}:
        datas.append((str(file), 'neural/runtime'))
datas.append((str(neural / 'models.json'), 'neural'))
if (neural / 'licenses').is_dir():
    datas.append((str(neural / 'licenses'), 'neural/licenses'))

# Keep the external program's DLLs beside it, outside Python's DLL namespace.
for file in tesseract.parent.iterdir():
    if file.suffix.lower() == ".dll" or file.name == "tesseract.exe":
        datas.append((str(file), "tesseract"))
datas.append((str(tesseract.parent / "tessdata"), "tesseract/tessdata"))
datas.append((str(tesseract.parent / "doc"), "licenses/tesseract"))
for file in (project / "vendor/tessdata").glob("*.traineddata"):
    datas.append((str(file), "tesseract/tessdata"))
if (project / "vendor/tessdata/LICENSE").is_file():
    datas.append((str(project / "vendor/tessdata/LICENSE"), "licenses/tessdata-fast"))

a = Analysis(
    [str(project / "packaging/entry.py")],
    pathex=[str(project / "src")], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "IPython", "tkinter", "matplotlib", "ocrmypdf", "pikepdf",
              "pymupdf.layout", "PySide6.QtWebEngineCore",
              "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)
# Qt uses Windows' native ICU forwarder. A developer PATH (for example Poppler)
# can make dependency discovery pick an incompatible ICU DLL with versioned
# exports instead. Let Windows supply this OS component, as in the source app.
a.binaries = [item for item in a.binaries if item[0].lower() != "icuuc.dll"]
pyz = PYZ(a.pure)
desktop = EXE(pyz, a.scripts, [], exclude_binaries=True, name="YuzuFile",
              console=False, debug=False, strip=False, upx=False)
worker = EXE(pyz, a.scripts, [], exclude_binaries=True, name="YuzuFile-worker",
             console=True, debug=False, strip=False, upx=False)
collection = COLLECT(desktop, worker, a.binaries, a.datas, strip=False, upx=False, name=f"YuzuFile-{__version__}")
