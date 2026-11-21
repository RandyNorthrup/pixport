"""Rendering geometry, colours and source handling.

Every geometry test runs against both an SVG and a PNG input: the two paths
must produce the same composition. (In 1.x the PNG path silently ignored zoom,
padding and the background colour.)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

from pixport.render import (
    MAX_EDGE,
    RenderOptions,
    SourceError,
    check_source,
    flatten,
    parse_color,
    render,
    render_preview,
    source_size,
)

RED = (255, 0, 0)
BLUE = (0, 0, 255)


@pytest.fixture(params=["square_svg", "square_png"])
def square(request: pytest.FixtureRequest) -> Path:
    """Run the test once with the SVG and once with the PNG square."""
    path: Path = request.getfixturevalue(request.param)
    return path


def test_full_fit_fills_canvas(square: Path) -> None:
    img = render(square, 100, 100, RenderOptions())
    assert img.mode == "RGBA"
    assert img.getpixel((0, 0)) == (*RED, 255)
    assert img.getpixel((99, 99)) == (*RED, 255)


def test_padding_insets_artwork(square: Path) -> None:
    img = render(square, 100, 100, RenderOptions(padding=20))
    assert img.getpixel((5, 5))[3] == 0
    assert img.getbbox() == (20, 20, 80, 80)
    assert img.getpixel((50, 50)) == (*RED, 255)


def test_zoom_shrinks_artwork(square: Path) -> None:
    img = render(square, 100, 100, RenderOptions(zoom=0.5))
    assert img.getpixel((10, 10))[3] == 0
    assert img.getbbox() == (25, 25, 75, 75)


@pytest.mark.parametrize("zoom", [1.5, 5.0])
def test_zoom_never_enlarges_past_fit(square: Path, zoom: float) -> None:
    assert render(square, 100, 100, RenderOptions(zoom=zoom)).getbbox() == (0, 0, 100, 100)


def test_zoom_has_lower_bound(square: Path) -> None:
    tiny = render(square, 100, 100, RenderOptions(zoom=0.0))
    assert tiny.getbbox() == (45, 45, 55, 55)  # clamped to 10 %


def test_opaque_uses_chosen_background(square: Path) -> None:
    img = render(square, 100, 100, RenderOptions(padding=20, transparent=False, background=BLUE))
    assert img.mode == "RGB"
    assert img.getpixel((2, 2)) == BLUE
    assert img.getpixel((50, 50)) == RED


def test_aspect_ratio_is_preserved(wide_svg: Path) -> None:
    img = render(wide_svg, 100, 100, RenderOptions())
    assert img.getbbox() == (0, 25, 100, 75)


def test_raster_is_upscaled_to_fit(square_png: Path) -> None:
    img = render(square_png, 400, 400, RenderOptions())
    assert img.getbbox() == (0, 0, 400, 400)


def test_svgz_is_supported(square_svgz: Path) -> None:
    assert render(square_svgz, 50, 50, RenderOptions()).getpixel((25, 25)) == (*RED, 255)


@pytest.mark.parametrize("suffix", [".jpg", ".webp", ".bmp", ".gif", ".tiff"])
def test_other_raster_inputs(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"in{suffix}"
    Image.new("RGB", (40, 20), RED).save(path)
    assert source_size(path) == (40, 20)
    img = render(path, 80, 80, RenderOptions())
    assert img.getbbox() == (0, 20, 80, 60)


def test_svg_source_size(wide_svg: Path) -> None:
    assert source_size(wide_svg) == (200, 100)


@pytest.mark.parametrize(("w", "h"), [(0, 10), (10, 0), (MAX_EDGE + 1, 10)])
def test_rejects_bad_canvas(square_svg: Path, w: int, h: int) -> None:
    with pytest.raises(ValueError, match="outside"):
        render(square_svg, w, h, RenderOptions())


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="not found"):
        check_source(tmp_path / "nope.svg")


def test_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hi", encoding="utf-8")
    with pytest.raises(SourceError, match="Unsupported"):
        check_source(path)


def test_broken_svg_raises_source_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.svg"
    path.write_text("<svg", encoding="utf-8")
    with pytest.raises(SourceError, match="Cannot render SVG"):
        render(path, 10, 10, RenderOptions())


def test_broken_raster_raises_source_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.png"
    path.write_bytes(b"not a png")
    with pytest.raises(SourceError, match="Cannot read image"):
        source_size(path)


def test_edited_svg_is_remeasured(tmp_path: Path) -> None:
    path = tmp_path / "live.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>', encoding="utf-8"
    )
    assert source_size(path) == (10, 10)
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="20"/>', encoding="utf-8"
    )
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert source_size(path) == (30, 20)


def test_preview_matches_export_composition(square_svg: Path) -> None:
    options = RenderOptions(padding=100, zoom=0.8)
    full = render(square_svg, 1000, 500, options)
    preview = render_preview(square_svg, 1000, 500, options, (200, 200))
    assert preview.size == (200, 100)
    full_box, preview_box = full.getbbox(), preview.getbbox()
    assert full_box is not None
    assert preview_box is not None
    assert [round(v / 5) for v in full_box] == list(preview_box)


def test_preview_never_upscales(square_svg: Path) -> None:
    assert render_preview(square_svg, 50, 50, RenderOptions(), (500, 500)).size == (50, 50)


def test_parse_color() -> None:
    assert parse_color("#0f172a") == (15, 23, 42)
    assert parse_color(" white ") == (255, 255, 255)
    assert parse_color("rgb(1,2,3)") == (1, 2, 3)
    with pytest.raises(ValueError, match="Not a colour"):
        parse_color("not-a-colour")


def test_flatten_composites_onto_background() -> None:
    clear = Image.new("RGBA", (4, 4), (255, 0, 0, 0))
    flat = flatten(clear, BLUE)
    assert flat.mode == "RGB"
    assert flat.getpixel((1, 1)) == BLUE
    rgb = Image.new("RGB", (2, 2), RED)
    assert flatten(rgb, BLUE) is rgb


def test_options_opaque_copy() -> None:
    opts = RenderOptions(padding=3, zoom=0.5, transparent=True, background=BLUE)
    assert opts.opaque() == RenderOptions(3, 0.5, False, BLUE)
