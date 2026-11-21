"""Light and dark themes that follow the operating system's colour scheme."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


BASE_POINT_SIZE = 10.0


@dataclass(frozen=True)
class Theme:
    """Named colours used by the palette, the stylesheet and custom painting."""

    dark: bool
    window: str
    surface: str
    raised: str
    border: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_text: str
    checker_a: str
    checker_b: str


DARK = Theme(
    dark=True,
    window="#0e1016",
    surface="#161922",
    raised="#1e2230",
    border="#2a2f3f",
    text="#e8eaf2",
    muted="#9aa1b8",
    accent="#7c6cff",
    accent_hover="#9285ff",
    accent_text="#ffffff",
    checker_a="#232736",
    checker_b="#1a1d29",
)

LIGHT = Theme(
    dark=False,
    window="#f4f5fa",
    surface="#ffffff",
    raised="#eef0f7",
    border="#dde1ec",
    text="#161922",
    muted="#5b6178",
    accent="#5b4cf0",
    accent_hover="#6f61ff",
    accent_text="#ffffff",
    checker_a="#e9ebf3",
    checker_b="#ffffff",
)


def system_theme() -> Theme:
    """Return the theme matching the OS colour scheme (light when unknown)."""
    scheme = QGuiApplication.styleHints().colorScheme()
    return DARK if scheme == Qt.ColorScheme.Dark else LIGHT


def _palette(t: Theme) -> QPalette:
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.window,
        QPalette.ColorRole.WindowText: t.text,
        QPalette.ColorRole.Base: t.surface,
        QPalette.ColorRole.AlternateBase: t.raised,
        QPalette.ColorRole.ToolTipBase: t.raised,
        QPalette.ColorRole.ToolTipText: t.text,
        QPalette.ColorRole.PlaceholderText: t.muted,
        QPalette.ColorRole.Text: t.text,
        QPalette.ColorRole.Button: t.raised,
        QPalette.ColorRole.ButtonText: t.text,
        QPalette.ColorRole.BrightText: "#ff5c7a",
        QPalette.ColorRole.Highlight: t.accent,
        QPalette.ColorRole.HighlightedText: t.accent_text,
        QPalette.ColorRole.Link: t.accent,
    }
    for role, colour in roles.items():
        pal.setColor(role, QColor(colour))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.muted))
    return pal


def _asset(name: str) -> str:
    ref = resources.files("pixport") / "assets" / name
    # Package data is a real file for both pip installs and PyInstaller bundles.
    return Path(str(ref)).as_posix()


def _stylesheet(t: Theme) -> str:
    chevron = _asset(f"chevron-{'dark' if t.dark else 'light'}.svg")
    chevron_up = _asset(f"chevron-up-{'dark' if t.dark else 'light'}.svg")
    check = _asset("check.svg")
    return f"""
QMainWindow, QWidget#root {{ background: {t.window}; }}
QWidget#sidebar {{ background: {t.surface}; border-left: 1px solid {t.border}; }}
QLabel#brand {{ font-size: 17px; font-weight: 700; }}
QLabel#version, QLabel#muted, QLabel#hint {{ color: {t.muted}; }}
QLabel#section {{
    color: {t.muted}; font-size: 11px; font-weight: 700;
    letter-spacing: 1px; padding-top: 10px;
}}
QLabel#summary {{ color: {t.muted}; }}
QLabel#info {{ color: {t.muted}; padding: 4px 2px; }}
QComboBox, QLineEdit {{
    background: {t.raised}; border: 1px solid {t.border}; border-radius: 7px;
    padding: 5px 8px; min-height: 20px;
}}
QSpinBox {{
    background: {t.raised}; border: 1px solid {t.border}; border-radius: 7px;
    padding-left: 6px; min-height: 30px;
}}
QSpinBox:focus {{ border-color: {t.accent}; }}
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border; width: 22px; border: none; background: transparent;
}}
QSpinBox::up-button {{ subcontrol-position: top right; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; }}
QSpinBox::up-arrow {{ image: url({chevron_up}); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url({chevron}); width: 10px; height: 10px; }}
QComboBox:focus, QLineEdit:focus {{ border-color: {t.accent}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {t.surface}; border: 1px solid {t.border};
    selection-background-color: {t.accent}; selection-color: {t.accent_text};
}}
QPushButton {{
    background: {t.raised}; border: 1px solid {t.border}; border-radius: 7px;
    padding: 6px 12px;
}}
QPushButton:hover {{ border-color: {t.accent}; }}
QPushButton:focus {{ border-color: {t.accent}; }}
QPushButton:checked {{ background: {t.accent}; color: {t.accent_text}; border-color: {t.accent}; }}
QPushButton#primary {{
    background: {t.accent}; color: {t.accent_text}; border: none;
    font-weight: 700; font-size: 14px; padding: 10px 14px; border-radius: 9px;
}}
QPushButton#primary:hover {{ background: {t.accent_hover}; }}
QPushButton#primary:disabled {{ background: {t.border}; color: {t.muted}; }}
QPushButton#link {{
    background: transparent; border: none; color: {t.accent}; padding: 2px 4px;
    font-weight: 600;
}}
QSlider::groove:horizontal {{ height: 4px; background: {t.border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {t.accent}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
}}
QProgressBar {{
    background: {t.raised}; border: 1px solid {t.border}; border-radius: 6px;
    text-align: center; min-height: 12px; max-height: 12px; font-size: 10px;
}}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 5px; }}
QStatusBar {{
    background: {t.surface}; border-top: 1px solid {t.border}; color: {t.muted};
    padding-left: 10px;
}}
QScrollArea {{ border: none; background: transparent; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border: 1.5px solid {t.muted}; border-radius: 4px;
    background: {t.raised};
}}
QCheckBox::indicator:checked {{
    background: {t.accent}; border-color: {t.accent}; image: url({check});
}}
QCheckBox::indicator:focus {{ border-color: {t.accent}; }}
QMenuBar {{ background: {t.window}; }}
QMenuBar::item:selected, QMenu::item:selected {{
    background: {t.accent}; color: {t.accent_text};
}}
QMenu {{ background: {t.surface}; border: 1px solid {t.border}; }}
"""


def apply_theme(app: QApplication, theme: Theme) -> None:
    """Apply palette and stylesheet for ``theme`` to the whole application."""
    app.setStyle("Fusion")
    font = app.font()
    if font.pointSizeF() < BASE_POINT_SIZE:
        font.setPointSizeF(BASE_POINT_SIZE)
        app.setFont(font)
    app.setPalette(_palette(theme))
    app.setStyleSheet(_stylesheet(theme))
