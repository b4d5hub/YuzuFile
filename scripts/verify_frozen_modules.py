"""Verify executable bytecode and packaged source match this checkout."""
from pathlib import Path
from types import CodeType
import argparse
import zipfile

from PyInstaller.archive.readers import CArchiveReader
from yuzufile import __version__


def normalized(code):
    return code.replace(co_filename='',co_consts=tuple(normalized(c) if isinstance(c,CodeType) else c for c in code.co_consts))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--executables-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    folder=root/'dist'/f'yuzufile-{__version__}'
    modules=['__init__','cleanup','cleanup_preview','page_canvas','spreads','spread_preview','split_viewport','worker','ui','ui_style','ui_components','tool_wheel','organize_ui','icons','packaging_smoke','word_export','word_rtl','word_mapping','word_detailed_ocr','vision_runtime']
    modules+=['preview_tools','page_preview','page_grid','shaped_shell','icon_assets',
              'ocr_clean','engines','indra_engine','arabic_ocr','neural_text','unicode_overlay','neural_task','neural_markdown','operations','output_names','tool_window','merge_ui','organize',
              'system_tray','desktop_drag','desktop_instance','storage','supervisor','publication','cli']
    for name in ('yuzufile.exe','yuzufile-worker.exe'):
        archive=CArchiveReader(str(folder/name)).open_embedded_archive('PYZ.pyz')
        for module in modules:
            source=root/'src/yuzufile'/f'{module}.py'
            expected=normalized(compile(source.read_bytes(),str(source),'exec'))
            actual=normalized(archive.extract('yuzufile' if module=='__init__' else f'yuzufile.{module}'))
            assert actual==expected,f'{name}: stale module {module}'
        print(f'{name}: {len(modules)} modules match current source')
    if args.executables_only:return
    with zipfile.ZipFile(root/'dist'/f'yuzufile-Windows-{__version__}.zip') as archive:
        for module in modules:
            source=root/'src/yuzufile'/f'{module}.py'
            packed=archive.read(f'{folder.name}/SOURCE/src/yuzufile/{module}.py')
            assert packed==source.read_bytes(),f'ZIP: stale source {module}'
    print('ZIP: packaged source matches current source')


if __name__=='__main__':main()
