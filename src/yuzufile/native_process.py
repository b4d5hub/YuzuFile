"""Hide native OCR helper consoles inside the isolated Windows worker."""
import os
import subprocess


def hide_helper_windows():
    if os.name != "nt":
        return
    original = subprocess.Popen

    class HiddenPopen(original):
        def __init__(self, *args, **kwargs):
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)

    # Applied only in the dedicated conversion process before engines import
    # their subprocess aliases. The UI process is unaffected.
    subprocess.Popen = HiddenPopen

