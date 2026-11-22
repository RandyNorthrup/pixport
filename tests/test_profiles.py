"""Every profile writes the files, sizes and folder layout it promises."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from pixport import profiles as pf
from pixport.render import RenderOptions

BLUE = (0, 0, 255)


def _job(source: Path, out: Path, fmt: str = "png", **kw: object) -> pf.Job:
    return pf.Job(source, out, fmt, **kw)  # type: ignore[arg-type]


def _run(profile_id: str, job: pf.Job) -> list[Path]:
    return pf.get_profile(profile_id).run(job)


# ── convert ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("fmt", pf.CONVERT_FORMATS)
def test_convert_every_format(square_svg: Path, out_dir: Path, fmt: str) -> None:
    (path,) = _run("convert", _job(square_svg, out_dir, fmt, width=64, height=32))
    assert path.name == f"square_64x32.{fmt}"
    if fmt != "pdf":
        with Image.open(path) as img:
            assert img.size == (64, 32)
            if fmt in pf.OPAQUE_FORMATS:
                assert img.mode == "RGB"
    else:
        assert path.read_bytes().startswith(b"%PDF")


def test_convert_never_overwrites(square_svg: Path, out_dir: Path) -> None:
    first = _run("convert", _job(square_svg, out_dir, width=10, height=10))
    second = _run("convert", _job(square_svg, out_dir, width=10, height=10))
    assert first[0].name == "square_10x10.png"
    assert second[0].name == "square_10x10_1.png"


def test_jpeg_alias_accepted(square_svg: Path, out_dir: Path) -> None:
    (path,) = _run("convert", _job(square_svg, out_dir, "JPEG", width=8, height=8))
    assert path.suffix == ".jpg"


def test_unsupported_format_rejected(square_svg: Path, out_dir: Path) -> None:
    with pytest.raises(ValueError, match="writes ico"):
        _run("windows-ico", _job(square_svg, out_dir, "png"))


def test_opaque_png_uses_background(square_svg: Path, out_dir: Path) -> None:
    opts = RenderOptions(padding=10, transparent=False, background=BLUE)
    (path,) = _run("convert", _job(square_svg, out_dir, width=40, height=40, options=opts))
    with Image.open(path) as img:
        assert img.mode == "RGB"
        assert img.getpixel((1, 1)) == BLUE


# ── icon containers ─────────────────────────────────────────────────────────


def test_windows_ico_has_every_size(square_svg: Path, out_dir: Path) -> None:
    (path,) = _run("windows-ico", _job(square_svg, out_dir, "ico"))
    assert path.name == "square.ico"
    with Image.open(path) as ico:
        sizes = {s[0] for s in ico.info["sizes"]}
    assert sizes == set(pf.WINDOWS_ICO_SIZES)


def test_ico_frames_rendered_per_size(tmp_path: Path, out_dir: Path) -> None:
    """A 1 px line at 256 px vanishes when downsampled to 16 but survives a native render."""
    svg = tmp_path / "line.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
        '<rect x="0" y="0" width="16" height="1" fill="#000"/></svg>',
        encoding="utf-8",
    )
    (path,) = _run("windows-ico", _job(svg, out_dir, "ico"))
    with Image.open(path) as ico:
        ico.size = (16, 16)
        ico.load()
        assert ico.convert("RGBA").getpixel((8, 0))[3] == 255


def test_macos_icns_sizes(square_svg: Path, out_dir: Path) -> None:
    (path,) = _run("macos-icns", _job(square_svg, out_dir, "icns"))
    with Image.open(path) as icns:
        slots = set(icns.info["sizes"])
    # Every point size at 1x and 2x, including the 16 px image Pillow's writer omits.
    assert slots == {(pt, pt, sc) for pt in (16, 32, 128, 256, 512) for sc in (1, 2)}


def test_icns_container_layout(square_svg: Path, out_dir: Path) -> None:
    """Header, total length and one PNG element per iconutil type, in order."""
    import struct

    png_signature = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    (path,) = _run("macos-icns", _job(square_svg, out_dir, "icns"))
    data = path.read_bytes()
    assert data[:4] == b"icns"
    assert struct.unpack(">I", data[4:8])[0] == len(data)
    offset, kinds = 8, []
    while offset < len(data):
        kind, length = (
            data[offset : offset + 4],
            struct.unpack(">I", data[offset + 4 : offset + 8])[0],
        )
        assert data[offset + 8 : offset + 16] == png_signature
        kinds.append(kind)
        offset += length
    assert offset == len(data)
    assert kinds == [k for k, _ in pf.ICNS_ELEMENTS]


def test_icns_frames_rendered_per_size(tmp_path: Path, out_dir: Path) -> None:
    svg = tmp_path / "line.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
        '<rect x="0" y="0" width="16" height="1" fill="#000"/></svg>',
        encoding="utf-8",
    )
    (path,) = _run("macos-icns", _job(svg, out_dir, "icns"))
    with Image.open(path) as icns:
        icns.size = (16, 16)
        icns.load(scale=1)
        assert icns.size == (16, 16)
        assert icns.convert("RGBA").getpixel((8, 0))[3] == 255


# ── folder layouts ──────────────────────────────────────────────────────────


def test_linux_hicolor_layout(square_svg: Path, out_dir: Path) -> None:
    written = _run("linux", _job(square_svg, out_dir))
    root = out_dir / "square-linux" / "hicolor"
    for size in pf.LINUX_HICOLOR_SIZES:
        png = root / f"{size}x{size}" / "apps" / "square.png"
        with Image.open(png) as img:
            assert img.size == (size, size)
    assert (root / "scalable" / "apps" / "square.svg").read_bytes() == square_svg.read_bytes()
    assert len(written) == len(pf.LINUX_HICOLOR_SIZES) + 1


def test_linux_raster_source_has_no_scalable(square_png: Path, out_dir: Path) -> None:
    _run("linux", _job(square_png, out_dir))
    assert not (out_dir / "square-linux" / "hicolor" / "scalable").exists()


@pytest.mark.parametrize("fmt", ["png", "webp"])
def test_android_layout(square_svg: Path, out_dir: Path, fmt: str) -> None:
    _run("android", _job(square_svg, out_dir, fmt))
    root = out_dir / "square-android"
    for folder, size in pf.ANDROID_MIPMAPS:
        with Image.open(root / folder / f"ic_launcher.{fmt}") as img:
            assert img.size == (size, size)
    with Image.open(root / "playstore-icon.png") as store:
        assert store.size == (512, 512)
        assert store.format == "PNG"


def test_android_adaptive_icon(square_svg: Path, out_dir: Path) -> None:
    import xml.etree.ElementTree as ET

    _run("android", _job(square_svg, out_dir, options=RenderOptions(background=BLUE)))
    root = out_dir / "square-android"
    for folder, legacy in pf.ANDROID_MIPMAPS:
        layer = round(legacy * 108 / 48)
        with Image.open(root / folder / "ic_launcher_foreground.png") as fg:
            assert fg.size == (layer, layer)
            # The red square fits the square inscribed in the 66 dp safe circle, centred,
            # so its corners survive a circular launcher mask.
            inset = round(layer * (108 - 66 / 2**0.5) / 2 / 108)
            corner = (inset - layer / 2) * 2**0.5
            assert abs(corner) <= layer * 33 / 108 + 1
            assert fg.getbbox() == (inset, inset, layer - inset, layer - inset)
        with Image.open(root / folder / "ic_launcher_monochrome.png") as mono:
            assert mono.convert("RGBA").getpixel((layer // 2, layer // 2)) == (255, 255, 255, 255)
            assert mono.convert("RGBA").getpixel((0, 0))[3] == 0
        with Image.open(root / folder / "ic_launcher_round.png") as rnd:
            px = rnd.convert("RGBA")
            assert px.size == (legacy, legacy)
            assert px.getpixel((0, 0))[3] == 0  # outside the circle
            assert px.getpixel((legacy // 2, 2))[:3] == BLUE  # circle edge, background colour
            assert px.getpixel((legacy // 2, legacy // 2))[:3] == (255, 0, 0)

    ns = "{http://schemas.android.com/apk/res/android}drawable"
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        icon = ET.parse(root / "mipmap-anydpi-v26" / name).getroot()  # noqa: S314 - own output
        assert icon.tag == "adaptive-icon"
        assert [(c.tag, c.get(ns)) for c in icon] == [
            ("background", "@color/ic_launcher_background"),
            ("foreground", "@mipmap/ic_launcher_foreground"),
            ("monochrome", "@mipmap/ic_launcher_monochrome"),
        ]
    colour = ET.parse(root / "values" / "ic_launcher_background.xml").getroot()  # noqa: S314
    assert colour.find("color").text == "#0000ff"  # type: ignore[union-attr]


def test_ios_appiconset(square_svg: Path, out_dir: Path) -> None:
    _run("ios", _job(square_svg, out_dir, options=RenderOptions(padding=50, background=BLUE)))
    root = out_dir / "square-ios" / "AppIcon.appiconset"
    contents = json.loads((root / "Contents.json").read_text(encoding="utf-8"))
    assert len(contents["images"]) == len(pf.IOS_APPICON_SLOTS)
    for entry in contents["images"]:
        point = float(entry["size"].split("x")[0])
        scale = int(entry["scale"].rstrip("x"))
        with Image.open(root / entry["filename"]) as img:
            assert img.size == (round(point * scale),) * 2
            # App Store Connect rejects alpha: always opaque, padding uses the background.
            assert img.mode == "RGB"
            assert img.getpixel((0, 0)) == BLUE
    assert any(e["idiom"] == "ios-marketing" for e in contents["images"])
    assert any(e["size"] == "83.5x83.5" for e in contents["images"])


def test_web_favicons(square_svg: Path, out_dir: Path) -> None:
    _run("web", _job(square_svg, out_dir, options=RenderOptions(background=BLUE)))
    root = out_dir / "square-web"
    expected = {
        "favicon.ico",
        "favicon-16x16.png",
        "favicon-32x32.png",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "site.webmanifest",
        "favicon.svg",
        "head-snippet.html",
    }
    assert {p.name for p in root.iterdir()} == expected
    with Image.open(root / "favicon.ico") as ico:
        assert {s[0] for s in ico.info["sizes"]} == set(pf.FAVICON_ICO_SIZES)
    with Image.open(root / "apple-touch-icon.png") as touch:
        assert touch.size == (180, 180)
        assert touch.mode == "RGB"
    manifest = json.loads((root / "site.webmanifest").read_text(encoding="utf-8"))
    assert manifest["background_color"] == "#0000ff"
    assert [i["sizes"] for i in manifest["icons"]] == ["192x192", "512x512"]
    snippet = (root / "head-snippet.html").read_text(encoding="utf-8")
    assert 'href="/favicon.svg"' in snippet
    assert 'rel="manifest"' in snippet


def test_web_raster_source_has_no_svg(square_png: Path, out_dir: Path) -> None:
    _run("web", _job(square_png, out_dir))
    root = out_dir / "square-web"
    assert not (root / "favicon.svg").exists()
    assert "favicon.svg" not in (root / "head-snippet.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("profile_id", "sizes"),
    [
        ("wallpaper-desktop", pf.DESKTOP_WALLPAPERS),
        ("wallpaper-phone", pf.PHONE_WALLPAPERS),
        ("wallpaper-tablet-portrait", pf.TABLET_PORTRAIT_WALLPAPERS),
        ("wallpaper-tablet-landscape", pf.TABLET_LANDSCAPE_WALLPAPERS),
    ],
)
def test_wallpapers(
    square_svg: Path, out_dir: Path, profile_id: str, sizes: tuple[tuple[int, int], ...]
) -> None:
    written = _run(profile_id, _job(square_svg, out_dir, "jpg"))
    assert len(written) == len(sizes)
    for path, (w, h) in zip(written, sizes, strict=True):
        assert path.parent.name == f"square-{profile_id.replace('wallpaper', 'wallpapers')}"
        with Image.open(path) as img:
            assert img.size == (w, h)
            assert img.format == "JPEG"


def test_folder_exports_never_overwrite(square_svg: Path, out_dir: Path) -> None:
    _run("android", _job(square_svg, out_dir))
    _run("android", _job(square_svg, out_dir))
    assert (out_dir / "square-android").is_dir()
    assert (out_dir / "square-android_1").is_dir()


# ── registry and progress ───────────────────────────────────────────────────


def test_profile_ids_unique_and_complete() -> None:
    ids = [p.id for p in pf.PROFILES]
    assert len(ids) == len(set(ids))
    assert "convert" in ids


def test_unknown_profile() -> None:
    with pytest.raises(KeyError, match="Choose one of"):
        pf.get_profile("nope")


def test_preview_size_is_largest_output() -> None:
    assert pf.get_profile("convert").preview_size(300, 200) == (300, 200)
    assert pf.get_profile("windows-ico").preview_size(1, 1) == (256, 256)
    assert pf.get_profile("wallpaper-desktop").preview_size(1, 1) == (5120, 2880)


@pytest.mark.parametrize("profile", pf.PROFILES, ids=lambda p: p.id)
def test_progress_reaches_total(square_svg: Path, out_dir: Path, profile: pf.Profile) -> None:
    calls: list[tuple[int, int]] = []
    job = _job(square_svg, out_dir, profile.formats[0], width=32, height=32)
    profile.run(job, lambda done, total: calls.append((done, total)))
    assert calls
    assert calls[-1][0] == calls[-1][1]


def test_progress_can_cancel(square_svg: Path, out_dir: Path) -> None:
    class StopError(Exception):
        pass

    def stop(done: int, _total: int) -> None:
        if done == 2:
            raise StopError

    with pytest.raises(StopError):
        pf.get_profile("linux").run(_job(square_svg, out_dir), stop)
    written = list((out_dir / "square-linux").rglob("*.png"))
    assert len(written) == 2


def test_unique_path(tmp_path: Path) -> None:
    target = tmp_path / "icon.ico"
    assert pf.unique_path(target) == target
    target.write_bytes(b"x")
    assert pf.unique_path(target).name == "icon_1.ico"
    (tmp_path / "icon_1.ico").write_bytes(b"x")
    assert pf.unique_path(target).name == "icon_2.ico"


def test_padding_scales_with_output_size(square_svg: Path, out_dir: Path) -> None:
    """Padding is set at the largest size; smaller sizes keep the same proportion.

    In 1.x the same absolute padding hit every size, so 64 px of padding left a
    16 px icon with a 1 px artwork.
    """
    _run("linux", _job(square_svg, out_dir, options=RenderOptions(padding=64)))
    root = out_dir / "square-linux" / "hicolor"
    with Image.open(root / "512x512" / "apps" / "square.png") as big:
        assert big.getbbox() == (64, 64, 448, 448)
    with Image.open(root / "16x16" / "apps" / "square.png") as small:
        assert small.getbbox() == (2, 2, 14, 14)


def test_wallpaper_padding_scales(square_svg: Path, out_dir: Path) -> None:
    written = _run(
        "wallpaper-desktop", _job(square_svg, out_dir, options=RenderOptions(padding=288))
    )
    sizes = dict(zip(pf.DESKTOP_WALLPAPERS, written, strict=True))
    with Image.open(sizes[(5120, 2880)]) as big:
        assert big.getbbox() == (1408, 288, 3712, 2592)
    with Image.open(sizes[(1280, 720)]) as small:
        assert small.getbbox() == (352, 72, 928, 648)
