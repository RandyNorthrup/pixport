"""PyInstaller entry point: the desktop app. A file argument is opened in the window."""

import sys

from pixport.gui.app import main

sys.exit(main())
