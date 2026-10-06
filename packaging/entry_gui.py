"""Frozen entry point of the windowed app (Notirua.app, Notirua.exe, AppRun)."""

import sys

from notirua.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
