import sys

if "--worker" in sys.argv:
    from yuzufile.worker import main
else:
    from yuzufile.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

