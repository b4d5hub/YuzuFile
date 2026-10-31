import sys

from yuzufile.languages import tesseract_environment, tesseract_executable


def test_packaged_app_prefers_its_own_ocr_runtime(tmp_path, monkeypatch):
    folder = tmp_path / "bundle" / "tesseract"
    folder.mkdir(parents=True)
    executable = folder / "tesseract.exe"
    executable.write_bytes(b"test stub")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(folder.parent), raising=False)
    monkeypatch.setattr("yuzufile.languages.shutil.which", lambda _: "C:/other/tesseract.exe")
    monkeypatch.setenv("TESSDATA_PREFIX", "C:/other/languages")
    assert tesseract_executable() == str(executable)
    environment = tesseract_environment()
    assert environment["TESSDATA_PREFIX"] == str(folder / "tessdata")
    assert environment["PATH"].startswith(str(folder))
