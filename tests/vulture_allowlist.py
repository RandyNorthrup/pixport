"""Names vulture cannot see being used.

Qt calls these event handlers itself; nothing in Python references them.
"""

# ruff: noqa: B018
from pixport.gui.app import MainWindow
from pixport.gui.widgets import PreviewCanvas

PreviewCanvas.paintEvent
PreviewCanvas.dragEnterEvent
PreviewCanvas.dropEvent
MainWindow.preview_idle  # read by tests and tools/screenshots.py
