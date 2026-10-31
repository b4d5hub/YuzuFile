"""Shared frozen entry point: windowed desktop and hidden console worker."""
import multiprocessing
import sys


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "--neural-task" in sys.argv:
        from yuzufile.neural_task import main
    elif "--worker" in sys.argv:
        from yuzufile.worker import main
    elif "--smoke-ui-report" in sys.argv:
        from yuzufile.packaging_smoke import main
    else:
        from yuzufile.cli import main
    raise SystemExit(main())
