"""Frozen entry point of the command line (notirua-cli), next to the windowed app."""

import sys

from notirua.cli import main

if __name__ == "__main__":
    sys.exit(main())
