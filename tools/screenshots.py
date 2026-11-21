"""Capture README screenshots of the real app window, light and dark.

Usage:  python tools/screenshots.py SOURCE OUT_DIR

Renders the actual MainWindow offscreen, so screenshots always match the code.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont

from pixport.gui import app as gui_app
from pixport.gui import theme
from pixport.gui.app import MainWindow, create_app

SCENES = (
    ("convert", "png", True),
    ("windows-ico", "ico", True),
    ("ios", "png", False),
    ("wallpaper-desktop", "png", False),
)


def main() -> int:
    """Write <scene>-<light|dark>.png for each scene."""
    source, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(["pixport"])
    # Offscreen Qt has no platform font; use the system UI face so text matches a real run.
    app.setFont(QFont("Segoe UI" if sys.platform == "win32" else "Inter", 10))
    scratch = tempfile.TemporaryDirectory()
    settings = QSettings(str(Path(scratch.name) / "screens.ini"), QSettings.Format.IniFormat)
    for name, chosen in (("light", theme.LIGHT), ("dark", theme.DARK)):
        gui_app.system_theme = lambda chosen=chosen: chosen
        window = MainWindow(settings)
        window.apply_system_theme()
        window.resize(1180, 720)
        window.show()
        window.load_source(source)
        window.background = (15, 23, 42) if name == "dark" else (241, 245, 249)
        for profile_id, fmt, transparent in SCENES:
            window.profile_combo.setCurrentIndex(window.profile_combo.findData(profile_id))
            window.format_combo.setCurrentText(fmt.upper())
            window.transparent_chk.setChecked(transparent)
            window.padding_spin.setValue(64 if profile_id.startswith("wallpaper") else 0)
            window.zoom_slider.setValue(60 if profile_id.startswith("wallpaper") else 100)
            app.processEvents()
            window.refresh_preview()
            while not window.preview_idle or window._preview_shown < window._preview_seq:  # noqa: SLF001
                app.processEvents()
            app.processEvents()
            window.grab().save(str(out_dir / f"{profile_id}-{name}.png"))
        window.close()
    del settings
    scratch.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
