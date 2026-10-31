"""Developer build: a portable directory plus ZIP, with native OCR included."""
from pathlib import Path
import argparse
import importlib.metadata
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile


def write_launcher(root,output):
    """A stable workspace shortcut prevents accidentally reopening old builds."""
    if os.name!='nt':return
    def literal(path):return "'"+str(path).replace("'","''")+"'"
    shortcut=root/'yuzufile.lnk'
    executable=output/'yuzufile.exe'
    script=("$taskShell=New-Object -ComObject WScript.Shell; "
            f"$taskLink=$taskShell.CreateShortcut({literal(shortcut)}); "
            f"$taskLink.TargetPath={literal(executable)}; "
            f"$taskLink.WorkingDirectory={literal(output)}; "
            f"$taskLink.IconLocation={literal(executable)}; "
            "$taskLink.Description='yuzufile latest local build'; $taskLink.Save()")
    shell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.run([str(shell),'-NoProfile','-NonInteractive','-Command',script],
                   check=True,creationflags=subprocess.CREATE_NO_WINDOW)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-only", action="store_true", help="Refresh documentation/source and ZIP without rebuilding executables")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from yuzufile import __version__
    # Refuse a partial or locally changed model set before constructing the EXE.
    indra = root / 'vendor/neural/indra'
    manifest = json.loads((indra / 'ready.json').read_text(encoding='utf-8'))
    for name, record in manifest['files'].items():
        with (indra / name).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != record['sha256']:
                raise RuntimeError(f'Indra model checksum mismatch: {name}')
    arabic_print = root / 'vendor/neural/arabic-print'
    print_manifest = json.loads((arabic_print / 'ready.json').read_text(encoding='utf-8'))
    for name, record in print_manifest['files'].items():
        with (arabic_print / name).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != record['sha256']:
                raise RuntimeError(f'Arabic print model checksum mismatch: {name}')
    if not args.package_only:
        environment = os.environ.copy()
        for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
            environment[name] = '1'
        subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "packaging/yuzufile.spec"], cwd=root, env=environment, check=True)
    output = root / "dist" / f"yuzufile-{__version__}"
    # Refuse stale PyInstaller archives before spending time packaging models.
    subprocess.run([sys.executable,str(root/'scripts/verify_frozen_modules.py'),'--executables-only'],
                   cwd=root,check=True)
    shutil.copy2(root / "packaging/START-HERE.txt", output / "START-HERE.txt")
    source = output / "SOURCE"
    source.mkdir(exist_ok=True)
    shutil.copytree(root / "src/yuzufile", source / "src/yuzufile", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("pyproject.toml", "requirements-windows.lock", "README.md"):
        shutil.copy2(root / name, source / name)
    shutil.copytree(root / "packaging", source / "packaging", dirs_exist_ok=True)
    shutil.copytree(root / "scripts", source / "scripts", dirs_exist_ok=True)
    shutil.copytree(root / "tests", source / "tests", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(root / "docs", source / "docs", dirs_exist_ok=True)
    shutil.copytree(root / "vendor/lucide", source / "vendor/lucide", dirs_exist_ok=True)
    licenses = output / "LICENSES"
    licenses.mkdir(exist_ok=True)
    shutil.copytree(root / "vendor/lucide", licenses / "Lucide", dirs_exist_ok=True)
    indra_licenses = licenses / 'Indra-models'
    indra_licenses.mkdir(exist_ok=True)
    shutil.copy2(indra / 'LICENSE', indra_licenses / 'LICENSE')
    shutil.copy2(indra / 'ready.json', indra_licenses / 'models.json')
    print_licenses = licenses / 'Kraken-Arabic-print'
    print_licenses.mkdir(exist_ok=True)
    for name in ('LICENSE', 'NOTICE', 'MODEL_CARD.md', 'ready.json'):
        shutil.copy2(arabic_print / name, print_licenses / name)
    records = []
    for package in importlib.metadata.distributions():
        name = package.metadata["Name"]
        records.append({"name": name, "version": package.version,
                        "license": package.metadata.get("License-Expression") or package.metadata.get("License", "See component source")})
        for file in package.files or []:
            if ".dist-info/" in str(file).replace("\\", "/") and any(
                word in str(file).lower() for word in ("license", "copying", "notice")
            ):
                original = Path(package.locate_file(file))
                if original.is_file():
                    destination = licenses / name / str(file).replace("\\", "/").split(".dist-info/", 1)[1]
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, destination)
    shutil.copytree(output / "_internal/licenses/tesseract", licenses / "Tesseract", dirs_exist_ok=True)
    if (output / "_internal/licenses/tessdata-fast").is_dir():
        shutil.copytree(output / "_internal/licenses/tessdata-fast", licenses / "tessdata-fast", dirs_exist_ok=True)
    (licenses / "build-environment.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    (licenses / "README.txt").write_text(
        "Component license texts and build-environment inventory. Inventory may include build-only packages.\n"
        "PyMuPDF/PyMuPDF4LLM are AGPL/commercial; application source is in SOURCE.\n"
        "This local development build has not undergone a full distribution-license audit.\n", encoding="utf-8")
    (output / 'PERSONAL-USE.txt').write_text(
        'This Indra-enabled build was prepared for personal use.\n'
        'Indra weights and their outputs are subject to LICENSES/Indra-models/LICENSE.\n'
        'The model license restricts competing products and includes output share-alike terms.\n'
        'This build is not cleared for public or commercial distribution.\n', encoding='utf-8')
    archive = root / 'dist' / f'yuzufile-Windows-{__version__}.zip'
    write_launcher(root,output)
    # Quantized model weights barely compress. Storing them avoids several
    # minutes of CPU work while preserving an ordinary extractable ZIP64.
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as bundle:
        for file in sorted(output.rglob('*')):
            if file.is_file():
                bundle.write(file, file.relative_to(output.parent),
                             compress_type=zipfile.ZIP_STORED if file.suffix == '.gguf' else zipfile.ZIP_DEFLATED)
    print(f"App: {output / 'yuzufile.exe'}\nArchive: {archive}")


if __name__ == "__main__":
    main()
