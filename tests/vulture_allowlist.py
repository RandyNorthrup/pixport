"""Names vulture cannot see being used.

Qt calls these event handlers itself; nothing in Python references them.
"""

# ruff: noqa: B018
from pixport.gui.widgets import PreviewCanvas

PreviewCanvas.paintEvent
PreviewCanvas.dragEnterEvent
PreviewCanvas.dropEvent
