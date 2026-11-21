"""``python -m pixport``: open the app, or run the command line if given arguments."""

from __future__ import annotations

import sys

from pixport.cli import main

if __name__ == "__main__":
    sys.exit(main())
