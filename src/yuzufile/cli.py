from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
import time
from pathlib import Path

from yuzufile.languages import installed_languages, tesseract_executable
from yuzufile.storage import Store
from yuzufile.operations import MODES


def main() -> int:
    parser = argparse.ArgumentParser(description="yuzufile: local PDF tools, OCR removal, fresh OCR and editable exports")
    parser.add_argument("--home", type=Path, help="App data/library directory (default: platform app data)")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("gui", help="Open the desktop app (also the default)")
    sub.add_parser("doctor", help="Check dependencies and list available OCR languages")
    convert = sub.add_parser("convert", help="Convert a PDF without opening the GUI")
    convert.add_argument("source", type=Path)
    convert.add_argument("--format", choices=[mode for mode in MODES if mode!='organize'], default="both",
                         help='Output operation combination; remove_ocr creates an image-only PDF without recognition')
    convert.add_argument("--compression", choices=["lossless", "balanced", "maximum"], default="balanced")
    convert.add_argument("--performance", choices=["low", "balanced", "high"], default="balanced")
    convert.add_argument("--output-directory", type=Path, help="Save outputs in a separate yuzufile folder here")
    convert.add_argument('--split-order', choices=['rl','lr','tb','bt'], default='lr')
    convert.add_argument('--split-position', type=float, default=50)
    convert.add_argument('--split-parts', type=int, default=2, help='Output parts per selected page (2-12)')
    convert.add_argument('--split-pages', default='', help='All pages, or ranges such as 2-15,18')
    convert.add_argument('--no-straighten',action='store_true',help='Disable automatic straightening for cleanup')
    convert.add_argument('--no-trim',action='store_true',help='Disable margin trimming for cleanup')
    convert.add_argument('--cleanup-padding',type=float,default=3,help='Retained margin in mm (1-20)')
    convert.add_argument('--cleanup-pages',default='',help='Pages to clean; blank means all')
    convert.add_argument("--languages", nargs="+", default=[], metavar="CODE", help="Installed codes, e.g. eng fra ara")
    args = parser.parse_args()
    if args.command in {None, "gui"}:
        from yuzufile.ui import main as gui_main
        return gui_main(args.home)
    if args.command == "doctor":
        packages = {}
        for name in ("PySide6-Essentials", "PyMuPDF", "pymupdf4llm", "Pillow"):
            try:
                packages[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                packages[name] = "MISSING"
        languages = installed_languages()
        print(json.dumps({"python": sys.version.split()[0], "packages": packages,
                          "tesseract": tesseract_executable(), "languages": languages}, indent=2))
        return int(not languages or "MISSING" in packages.values())
    try:
        store = Store(args.home)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    try:
        from yuzufile.supervisor import Supervisor
        supervisor = Supervisor(store)
        store.recover()
        job_id = store.create(args.source, args.format, args.languages, args.compression, args.performance, args.output_directory,
                              {'direction':args.split_order,'position':args.split_position,'pages':args.split_pages,'parts':args.split_parts},
                              cleanup_settings={'straighten':not args.no_straighten,'trim':not args.no_trim,
                                                'padding_mm':args.cleanup_padding,'pages':args.cleanup_pages})
        last_stage = ""
        try:
            while store.get(job_id)["state"] in {"queued", "running"}:
                supervisor.tick()
                stage = store.get(job_id)["stage"]
                if stage != last_stage:
                    print(stage, file=sys.stderr)
                    last_stage = stage
                time.sleep(0.1)
        except KeyboardInterrupt:
            supervisor.shutdown()
            return 130
        job = store.get(job_id)
        print(json.dumps({"job": job, "directory": str(store.result_directory(job_id)),
                          "artifacts": store.artifacts(job_id)}, indent=2))
        return int(job["state"] != "succeeded")
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        store.close()
