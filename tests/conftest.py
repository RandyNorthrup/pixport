"""Shared fixtures.

Core tests never touch Qt. GUI tests request ``qt_app``, which creates the one
QApplication a process may have.
"""

from __future__ import annotations

import gzip
import os
from pathlib import Path

import pytest
from PIL import Image

# Qt needs a platform plugin even when nothing is shown.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RED_SQUARE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
    '<rect width="100" height="100" fill="#ff0000"/></svg>'
)


@pytest.fixture(scope="session")
def qt_app() -> object:
    """The single QApplication shared by every GUI test."""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def square_svg(tmp_path: Path) -> Path:
    """A 100x100 SVG filled edge to edge with red.

    Filling the viewport makes padding and zoom observable: any inset shows up
    as border pixels that are not red.
    """
    path = tmp_path / "square.svg"
    path.write_text(RED_SQUARE_SVG, encoding="utf-8")
    return path


@pytest.fixture
def square_svgz(tmp_path: Path) -> Path:
    """The same red square, gzip-compressed."""
    path = tmp_path / "square.svgz"
    path.write_bytes(gzip.compress(RED_SQUARE_SVG.encode()))
    return path


@pytest.fixture
def wide_svg(tmp_path: Path) -> Path:
    """A 200x100 SVG, to check aspect ratio is preserved."""
    path = tmp_path / "wide.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
        '<rect width="200" height="100" fill="#0000ff"/></svg>',
        encoding="utf-8",
    )
    return path


@pytest.fixture
def square_png(tmp_path: Path) -> Path:
    """A 100x100 opaque red PNG, the raster twin of square_svg."""
    path = tmp_path / "square.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(path)
    return path


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    """An empty output folder."""
    path = tmp_path / "out"
    path.mkdir()
    return path
