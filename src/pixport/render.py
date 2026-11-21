"""Rendering: load one source image and place it on a canvas of any size.

This module has no Qt dependency. The GUI, the command line and the tests all
call :func:`render`, so a preview, an export and a test of the same settings
produce the same pixels.

Geometry, for a canvas of ``width`` x ``height``:

1. ``padding`` pixels are reserved on every side, leaving a work area.
2. The artwork is scaled to fit inside the work area, preserving its aspect
   ratio. Vector sources are rendered at that size; raster sources are
   resampled to it (up or down).
3. ``zoom`` (0.1 to 1.0) shrinks the fitted artwork further. It never enlarges
   past the fitted size.
4. The artwork is centred on the canvas, which is transparent or filled with
   ``background``.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import resvg_py
from PIL import Image, ImageColor

RGB = tuple[int, int, int]

#: File extensions treated as vector input.
VECTOR_SUFFIXES = frozenset({".svg", ".svgz"})
#: File extensions treated as raster input.
RASTER_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".ico"}
)
SUPPORTED_SUFFIXES = VECTOR_SUFFIXES | RASTER_SUFFIXES

MIN_ZOOM = 0.1
MAX_ZOOM = 1.0
#: Largest canvas edge accepted, in pixels. Guards against typos such as
#: 160000 that would try to allocate tens of gigabytes.
MAX_EDGE = 16384


class SourceError(ValueError):
    """The source file is missing, unsupported, or cannot be decoded."""


@dataclass(frozen=True)
class RenderOptions:
    """How artwork is placed on the canvas. Shared by every export."""

    padding: int = 0
    zoom: float = 1.0
    transparent: bool = True
    background: RGB = (255, 255, 255)

    def opaque(self) -> RenderOptions:
        """Return a copy that always fills the background (for no-alpha formats)."""
        return RenderOptions(self.padding, self.zoom, False, self.background)


def parse_color(value: str) -> RGB:
    """Parse a CSS colour (``#1e293b``, ``white``, ``rgb(0,0,0)``) into RGB.

    Raises:
        ValueError: if the value is not a colour Pillow recognises.
    """
    try:
        rgb = ImageColor.getrgb(value.strip())
    except ValueError as exc:
        raise ValueError(f"Not a colour: {value!r}") from exc
    return (rgb[0], rgb[1], rgb[2])


def is_vector(path: Path) -> bool:
    """True when the path is an SVG or SVGZ file."""
    return path.suffix.lower() in VECTOR_SUFFIXES


def check_source(path: Path) -> None:
    """Raise :class:`SourceError` unless ``path`` is an existing supported file."""
    if not path.is_file():
        raise SourceError(f"File not found: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise SourceError(f"Unsupported file type {path.suffix!r}. Supported: {supported}")


def _svg_png(path: Path, zoom: float | None = None) -> Image.Image:
    try:
        data = resvg_py.svg_to_bytes(svg_path=str(path), zoom=zoom)
    except (ValueError, OSError) as exc:
        raise SourceError(f"Cannot render SVG {path.name}: {exc}") from exc
    img = Image.open(io.BytesIO(bytes(data)))
    img.load()
    return img.convert("RGBA")


@lru_cache(maxsize=32)
def _svg_native_size(path: str, _mtime_ns: int) -> tuple[int, int]:
    # Keyed on mtime so an SVG edited while the app is open is re-measured.
    return _svg_png(Path(path)).size


def source_size(path: Path) -> tuple[int, int]:
    """Return the intrinsic pixel size of the source artwork."""
    check_source(path)
    if is_vector(path):
        return _svg_native_size(str(path), path.stat().st_mtime_ns)
    try:
        with Image.open(path) as img:
            width, height = img.size
            return (int(width), int(height))
    except (OSError, Image.DecompressionBombError) as exc:
        raise SourceError(f"Cannot read image {path.name}: {exc}") from exc


def _fitted_artwork(path: Path, box_w: int, box_h: int) -> Image.Image:
    """Return the artwork as RGBA, scaled to fit inside ``box_w`` x ``box_h``."""
    native_w, native_h = source_size(path)
    scale = min(box_w / native_w, box_h / native_h)
    target = (max(1, round(native_w * scale)), max(1, round(native_h * scale)))
    if is_vector(path):
        art = _svg_png(path, zoom=scale)
    else:
        try:
            with Image.open(path) as src:
                # Animated GIF/WebP and multi-frame ICO: the first frame is used.
                src.seek(0)
                art = src.convert("RGBA")
        except (OSError, Image.DecompressionBombError) as exc:
            raise SourceError(f"Cannot read image {path.name}: {exc}") from exc
    if art.size != target:
        art = art.resize(target, Image.Resampling.LANCZOS)
    return art


def render(path: Path, width: int, height: int, options: RenderOptions) -> Image.Image:
    """Render ``path`` onto a ``width`` x ``height`` canvas.

    Returns an RGBA image when ``options.transparent`` is true, otherwise RGB.

    Raises:
        SourceError: if the source cannot be read or rendered.
        ValueError: if the canvas size is outside 1..MAX_EDGE.
    """
    if not (1 <= width <= MAX_EDGE and 1 <= height <= MAX_EDGE):
        raise ValueError(f"Canvas {width}x{height} is outside 1..{MAX_EDGE} pixels")
    padding = max(0, options.padding)
    zoom = max(MIN_ZOOM, min(MAX_ZOOM, options.zoom))
    work_w = max(1, width - 2 * padding)
    work_h = max(1, height - 2 * padding)
    box_w = max(1, round(work_w * zoom))
    box_h = max(1, round(work_h * zoom))

    art = _fitted_artwork(path, box_w, box_h)
    offset = ((width - art.width) // 2, (height - art.height) // 2)

    if options.transparent:
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.alpha_composite(art, offset)
        return canvas
    canvas = Image.new("RGB", (width, height), options.background)
    canvas.paste(art, offset, mask=art)
    return canvas


def render_preview(
    path: Path,
    width: int,
    height: int,
    options: RenderOptions,
    max_size: tuple[int, int],
) -> Image.Image:
    """Render a scaled-down copy of what :func:`render` would produce.

    The canvas and padding shrink by the same factor, so the preview shows the
    exact composition of the full-size export at a fraction of the cost.
    """
    max_width, max_height = max_size
    scale = min(1.0, max_width / width, max_height / height)
    scaled = RenderOptions(
        padding=round(options.padding * scale),
        zoom=options.zoom,
        transparent=options.transparent,
        background=options.background,
    )
    return render(path, max(1, round(width * scale)), max(1, round(height * scale)), scaled)


def flatten(img: Image.Image, background: RGB) -> Image.Image:
    """Composite an image onto an opaque background and return RGB."""
    if img.mode == "RGB":
        return img
    rgba = img.convert("RGBA")
    canvas = Image.new("RGB", rgba.size, background)
    canvas.paste(rgba, mask=rgba)
    return canvas
