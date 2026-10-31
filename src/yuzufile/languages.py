"""Discover only recognition languages actually available to Tesseract."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

NAMES = {
    "eng": "English", "fra": "French", "ara": "Arabic", "spa": "Spanish",
    "deu": "German", "ita": "Italian", "por": "Portuguese", "rus": "Russian",
    "chi_sim": "Chinese (simplified)", "chi_tra": "Chinese (traditional)",
    "jpn": "Japanese", "kor": "Korean", "hin": "Hindi", "nld": "Dutch",
    "tur": "Turkish", "pol": "Polish", "ukr": "Ukrainian", "heb": "Hebrew",
}


def tesseract_executable() -> str | None:
    if getattr(sys, "frozen", False):
        bundled = Path(sys._MEIPASS) / "tesseract" / "tesseract.exe"
        if bundled.is_file():
            return str(bundled)
    found = shutil.which("tesseract")
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")):
            if base:
                folder = "Programs/Tesseract-OCR" if base == os.environ.get("LOCALAPPDATA") else "Tesseract-OCR"
                candidate = Path(base) / folder / "tesseract.exe"
                if candidate.is_file():
                    return str(candidate)
    return None


def tesseract_environment() -> dict[str, str]:
    environment = os.environ.copy()
    executable = tesseract_executable()
    if executable:
        environment["PATH"] = str(Path(executable).parent) + os.pathsep + environment.get("PATH", "")
        if getattr(sys, "frozen", False):
            environment["TESSDATA_PREFIX"] = str(Path(executable).parent / "tessdata")
    return environment


def installed_languages() -> list[str]:
    from yuzufile.indra_engine import available as indra_available
    from yuzufile.neural_text import available
    if available() or indra_available():
        return ['eng', 'fra', 'ara']
    executable = tesseract_executable()
    if not executable:
        return []
    try:
        result = subprocess.run(
            [executable, "--list-langs"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
            env=tesseract_environment(),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode:
        return []
    # osd is orientation/script detection data, not a recognition language.
    return sorted({line.strip() for line in result.stdout.splitlines()
                   if re.fullmatch(r"[\w/-]+", line.strip()) and line.strip() != "osd"})


def label(code: str) -> str:
    return f"{NAMES.get(code, code)} ({code})"
