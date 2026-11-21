"""Export profiles: what gets written, at which sizes, in which folder layout.

Every profile is one entry in :data:`PROFILES`. The GUI builds its menu from
this table and the command line accepts the same ids, so adding a profile here
adds it everywhere.

Writers never overwrite: a single-file export gets ``name_1.ext`` if
``name.ext`` exists, and a folder export gets ``folder_1`` if ``folder``
exists.
"""

from __future__ import annotations

import io
import json
import math
import shutil
import struct
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

from pixport.render import RenderOptions, flatten, is_vector, render

if TYPE_CHECKING:
    from pathlib import Path

#: progress(done, total) is called after each file. It may raise to cancel.
Progress = Callable[[int, int], None]

# ── size tables ─────────────────────────────────────────────────────────────

WINDOWS_ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
#: ICNS element types and their pixel size: the PNG-based set iconutil writes,
#: covering 16 to 512 pt at 1x and 2x (macOS 10.7 and later).
ICNS_ELEMENTS = (
    (b"icp4", 16),
    (b"icp5", 32),
    (b"ic11", 32),  # 16 pt @2x
    (b"icp6", 64),
    (b"ic12", 64),  # 32 pt @2x
    (b"ic07", 128),
    (b"ic08", 256),
    (b"ic13", 256),  # 128 pt @2x
    (b"ic09", 512),
    (b"ic14", 512),  # 256 pt @2x
    (b"ic10", 1024),  # 512 pt @2x
)
MACOS_ICNS_SIZES = tuple(sorted({px for _, px in ICNS_ELEMENTS}))
LINUX_HICOLOR_SIZES = (16, 22, 24, 32, 48, 64, 96, 128, 256, 512)
ANDROID_MIPMAPS = (
    ("mipmap-mdpi", 48),
    ("mipmap-hdpi", 72),
    ("mipmap-xhdpi", 96),
    ("mipmap-xxhdpi", 144),
    ("mipmap-xxxhdpi", 192),
)
ANDROID_PLAY_STORE = 512
#: Adaptive icon layers are 108 dp square; launchers may mask or move them, and
#: only the central 66 dp circle is guaranteed visible.
ANDROID_ADAPTIVE_DP = 108
ANDROID_SAFE_ZONE_DP = 66
#: The safe zone is a circle; artwork is fitted to the square inscribed in it so
#: corners stay visible under every launcher mask.
ANDROID_SAFE_SQUARE_DP = ANDROID_SAFE_ZONE_DP / math.sqrt(2)
#: Legacy round icons keep the artwork inside this share of the circle.
ANDROID_ROUND_ART = 0.62

_ADAPTIVE_XML = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
    <monochrome android:drawable="@mipmap/ic_launcher_monochrome"/>
</adaptive-icon>
"""
_BACKGROUND_XML = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_launcher_background">{colour}</color>
</resources>
"""

#: (idiom, point size, scale) for every slot of an Xcode AppIcon set,
#: covering iPhone, iPad and the App Store marketing icon.
IOS_APPICON_SLOTS: tuple[tuple[str, float, int], ...] = (
    ("iphone", 20, 2),
    ("iphone", 20, 3),
    ("iphone", 29, 2),
    ("iphone", 29, 3),
    ("iphone", 40, 2),
    ("iphone", 40, 3),
    ("iphone", 60, 2),
    ("iphone", 60, 3),
    ("ipad", 20, 1),
    ("ipad", 20, 2),
    ("ipad", 29, 1),
    ("ipad", 29, 2),
    ("ipad", 40, 1),
    ("ipad", 40, 2),
    ("ipad", 76, 1),
    ("ipad", 76, 2),
    ("ipad", 83.5, 2),
    ("ios-marketing", 1024, 1),
)

FAVICON_ICO_SIZES = (16, 32, 48)

DESKTOP_WALLPAPERS = (
    (1280, 720),
    (1366, 768),
    (1920, 1080),
    (2560, 1440),
    (3440, 1440),
    (3840, 2160),
    (5120, 2880),
)
PHONE_WALLPAPERS = (
    (750, 1334),
    (1080, 1920),
    (1080, 2400),
    (1170, 2532),
    (1179, 2556),
    (1290, 2796),
    (1440, 3040),
    (1440, 3200),
)
TABLET_PORTRAIT_WALLPAPERS = (
    (1536, 2048),
    (1600, 2560),
    (1640, 2360),
    (1668, 2388),
    (2048, 2732),
)
TABLET_LANDSCAPE_WALLPAPERS = tuple((h, w) for w, h in TABLET_PORTRAIT_WALLPAPERS)

RASTER_FORMATS = ("png", "jpg", "webp", "bmp")
CONVERT_FORMATS = ("png", "jpg", "webp", "bmp", "tiff", "pdf")
#: Formats with no alpha channel; artwork is flattened onto the background.
OPAQUE_FORMATS = frozenset({"jpg", "jpeg", "bmp", "pdf"})

JPEG_QUALITY = 95


# ── helpers ─────────────────────────────────────────────────────────────────


def unique_path(path: Path) -> Path:
    """Return ``path``, or ``stem_1``, ``stem_2``... if it already exists."""
    candidate = path
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        counter += 1
    return candidate


def save_image(img: Image.Image, path: Path, fmt: str, options: RenderOptions) -> None:
    """Write ``img`` in ``fmt``, flattening onto the background when the format has no alpha."""
    fmt = fmt.lower()
    if fmt in OPAQUE_FORMATS or not options.transparent:
        img = flatten(img, options.background)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt in {"jpg", "jpeg"}:
        img.save(path, "JPEG", quality=JPEG_QUALITY, subsampling=0, optimize=True)
    elif fmt == "webp":
        img.save(path, "WEBP", lossless=True)
    elif fmt == "pdf":
        img.save(path, "PDF", resolution=72.0)
    elif fmt in {"tif", "tiff"}:
        img.save(path, "TIFF", compression="tiff_lzw")
    elif fmt == "png":
        img.save(path, "PNG", optimize=True)
    else:
        img.save(path, fmt.upper())


def _square(job: Job, size: int, *, opaque: bool = False) -> Image.Image:
    return render(job.source, size, size, job.options_at(size, size, opaque=opaque))


def _icon_frames(job: Job, sizes: tuple[int, ...]) -> dict[int, Image.Image]:
    """Render every icon size on its own, not downsampled from one large image."""
    frames = {s: _square(job, s) for s in sorted(set(sizes))}
    if not job.options.transparent:
        frames = {s: flatten(f, job.options.background).convert("RGBA") for s, f in frames.items()}
    return frames


def _write_ico_file(job: Job, path: Path, sizes: tuple[int, ...]) -> None:
    frames = list(_icon_frames(job, sizes).values())
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[-1].save(path, "ICO", sizes=[f.size for f in frames], append_images=frames[:-1])


def icns_bytes(frames: dict[int, Image.Image]) -> bytes:
    """Encode an .icns container from PNG frames keyed by pixel size.

    Pillow's own writer has no 16 px element, so the container is built here:
    a 'icns' header and one PNG element per type in :data:`ICNS_ELEMENTS`.
    """
    encoded: dict[int, bytes] = {}
    for px, frame in frames.items():
        buf = io.BytesIO()
        frame.save(buf, "PNG", optimize=True)
        encoded[px] = buf.getvalue()
    body = b"".join(
        kind + struct.pack(">I", 8 + len(encoded[px])) + encoded[px] for kind, px in ICNS_ELEMENTS
    )
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


# ── jobs and profiles ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Job:
    """One export request."""

    source: Path
    out_dir: Path
    fmt: str = "png"
    width: int = 1024
    height: int = 1024
    options: RenderOptions = field(default_factory=RenderOptions)
    #: Canvas size the padding is expressed at. Profile.run sets it to the
    #: largest output size, so padding keeps the same proportion at every size.
    reference: tuple[int, int] | None = None

    def options_at(self, width: int, height: int, *, opaque: bool = False) -> RenderOptions:
        """Options for one output canvas, with padding scaled from the reference size."""
        opts = self.options
        if self.reference is not None:
            ref_w, ref_h = self.reference
            scale = min(width / ref_w, height / ref_h)
            opts = replace(opts, padding=round(opts.padding * scale))
        return opts.opaque() if opaque else opts

    @property
    def name(self) -> str:
        """Base name for written files, taken from the source file."""
        return self.source.stem


@dataclass(frozen=True)
class Profile:
    """An export preset."""

    id: str
    label: str
    group: str
    summary: str
    formats: tuple[str, ...]
    writer: Callable[[Job, Progress], list[Path]]
    #: Fixed canvas sizes; empty means the user's width x height is used.
    sizes: tuple[tuple[int, int], ...] = ()
    #: True when the profile forces an opaque background regardless of settings.
    forces_opaque: bool = False

    @property
    def uses_custom_size(self) -> bool:
        """True when the width and height controls apply to this profile."""
        return not self.sizes

    def preview_size(self, width: int, height: int) -> tuple[int, int]:
        """Canvas size the preview should show: the largest output size."""
        if not self.sizes:
            return (width, height)
        return max(self.sizes, key=lambda wh: wh[0] * wh[1])

    def run(self, job: Job, progress: Progress | None = None) -> list[Path]:
        """Validate the format and run the writer."""
        fmt = job.fmt.lower()
        if fmt == "jpeg":
            fmt = "jpg"
        if fmt not in self.formats:
            allowed = ", ".join(self.formats)
            raise ValueError(f"{self.label} writes {allowed}, not {job.fmt!r}")
        job = replace(job, fmt=fmt, reference=self.preview_size(job.width, job.height))
        return self.writer(job, progress or (lambda _done, _total: None))


# ── writers ─────────────────────────────────────────────────────────────────


def _write_convert(job: Job, progress: Progress) -> list[Path]:
    out = unique_path(job.out_dir / f"{job.name}_{job.width}x{job.height}.{job.fmt}")
    options = job.options_at(job.width, job.height)
    save_image(render(job.source, job.width, job.height, options), out, job.fmt, options)
    progress(1, 1)
    return [out]


def _write_ico(job: Job, progress: Progress) -> list[Path]:
    out = unique_path(job.out_dir / f"{job.name}.ico")
    _write_ico_file(job, out, WINDOWS_ICO_SIZES)
    progress(1, 1)
    return [out]


def _write_icns(job: Job, progress: Progress) -> list[Path]:
    out = unique_path(job.out_dir / f"{job.name}.icns")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(icns_bytes(_icon_frames(job, MACOS_ICNS_SIZES)))
    progress(1, 1)
    return [out]


def _write_linux(job: Job, progress: Progress) -> list[Path]:
    root = unique_path(job.out_dir / f"{job.name}-linux") / "hicolor"
    written: list[Path] = []
    total = len(LINUX_HICOLOR_SIZES) + int(is_vector(job.source))
    for i, size in enumerate(LINUX_HICOLOR_SIZES, 1):
        out = root / f"{size}x{size}" / "apps" / f"{job.name}.png"
        save_image(_square(job, size), out, "png", job.options)
        written.append(out)
        progress(i, total)
    if is_vector(job.source):
        scalable = root / "scalable" / "apps" / f"{job.name}.svg"
        scalable.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(job.source, scalable)
        written.append(scalable)
        progress(total, total)
    return written


def _hex_colour(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _android_layers(job: Job, legacy_px: int) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Foreground, monochrome and round-legacy images for one density.

    ``legacy_px`` is the density's 48 dp legacy size; adaptive layers are 108 dp.
    """
    layer_px = round(legacy_px * ANDROID_ADAPTIVE_DP / 48)
    user = job.options_at(layer_px, layer_px)
    inset = round(
        layer_px * (ANDROID_ADAPTIVE_DP - ANDROID_SAFE_SQUARE_DP) / 2 / ANDROID_ADAPTIVE_DP
    )
    foreground = render(
        job.source,
        layer_px,
        layer_px,
        replace(user, padding=inset + user.padding, transparent=True),
    )
    # Android 13 themed icons use only the alpha channel of the monochrome layer.
    monochrome = Image.new("RGBA", foreground.size, (255, 255, 255, 0))
    monochrome.putalpha(foreground.getchannel("A"))

    round_icon = Image.new("RGBA", (legacy_px, legacy_px), (0, 0, 0, 0))
    disc = Image.new("L", (legacy_px * 4, legacy_px * 4), 0)
    ImageDraw.Draw(disc).ellipse((0, 0, legacy_px * 4 - 1, legacy_px * 4 - 1), fill=255)
    disc = disc.resize((legacy_px, legacy_px), Image.Resampling.LANCZOS)
    round_icon.paste((*job.options.background, 255), (0, 0), disc)
    art_px = max(1, round(legacy_px * ANDROID_ROUND_ART))
    art = render(
        job.source, art_px, art_px, replace(job.options_at(art_px, art_px), transparent=True)
    )
    offset = (legacy_px - art_px) // 2
    round_icon.alpha_composite(art, (offset, offset))
    return foreground, monochrome, round_icon


def _write_android(job: Job, progress: Progress) -> list[Path]:
    root = unique_path(job.out_dir / f"{job.name}-android")
    written: list[Path] = []
    total = len(ANDROID_MIPMAPS) + 2
    transparent = replace(job.options, transparent=True)
    for i, (folder, size) in enumerate(ANDROID_MIPMAPS, 1):
        legacy = root / folder / f"ic_launcher.{job.fmt}"
        save_image(_square(job, size), legacy, job.fmt, job.options)
        foreground, monochrome, round_icon = _android_layers(job, size)
        layers = {
            f"ic_launcher_foreground.{job.fmt}": foreground,
            f"ic_launcher_monochrome.{job.fmt}": monochrome,
            f"ic_launcher_round.{job.fmt}": round_icon,
        }
        written.append(legacy)
        for filename, img in layers.items():
            out = root / folder / filename
            save_image(img, out, job.fmt, transparent)
            written.append(out)
        progress(i, total)

    anydpi = root / "mipmap-anydpi-v26"
    anydpi.mkdir(parents=True, exist_ok=True)
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        (anydpi / name).write_text(_ADAPTIVE_XML, encoding="utf-8")
        written.append(anydpi / name)
    values = root / "values" / "ic_launcher_background.xml"
    values.parent.mkdir(parents=True, exist_ok=True)
    values.write_text(
        _BACKGROUND_XML.format(colour=_hex_colour(job.options.background)), encoding="utf-8"
    )
    written.append(values)
    progress(total - 1, total)

    # Google Play requires a 512 px 32-bit PNG regardless of the launcher format.
    store = root / "playstore-icon.png"
    save_image(_square(job, ANDROID_PLAY_STORE), store, "png", job.options)
    written.append(store)
    progress(total, total)
    return written


def _ios_point(value: float) -> str:
    return f"{value:g}"


def _write_ios(job: Job, progress: Progress) -> list[Path]:
    root = unique_path(job.out_dir / f"{job.name}-ios") / "AppIcon.appiconset"
    # App Store Connect rejects icons with an alpha channel, so iOS is always opaque.
    opaque = job.options.opaque()
    pixel_sizes = sorted({round(pt * scale) for _, pt, scale in IOS_APPICON_SLOTS})
    written: list[Path] = []
    total = len(pixel_sizes) + 1
    for i, px in enumerate(pixel_sizes, 1):
        out = root / f"Icon-{px}.png"
        save_image(_square(job, px, opaque=True), out, "png", opaque)
        written.append(out)
        progress(i, total)
    images = [
        {
            "size": f"{_ios_point(pt)}x{_ios_point(pt)}",
            "idiom": idiom,
            "filename": f"Icon-{round(pt * scale)}.png",
            "scale": f"{scale}x",
        }
        for idiom, pt, scale in IOS_APPICON_SLOTS
    ]
    contents = root / "Contents.json"
    contents.write_text(
        json.dumps({"images": images, "info": {"version": 1, "author": "pixport"}}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    written.append(contents)
    progress(total, total)
    return written


_FAVICON_SNIPPET = """\
<link rel="icon" href="/favicon.ico" sizes="48x48">
{svg_line}<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
"""


def _write_web(job: Job, progress: Progress) -> list[Path]:
    root = unique_path(job.out_dir / f"{job.name}-web")
    root.mkdir(parents=True)
    opaque = job.options.opaque()
    steps: list[tuple[str, Callable[[Path], None]]] = [
        ("favicon.ico", lambda p: _write_ico_file(job, p, FAVICON_ICO_SIZES)),
        ("favicon-16x16.png", lambda p: save_image(_square(job, 16), p, "png", job.options)),
        ("favicon-32x32.png", lambda p: save_image(_square(job, 32), p, "png", job.options)),
        # iOS draws a black square behind transparent touch icons, so this one is opaque.
        (
            "apple-touch-icon.png",
            lambda p: save_image(_square(job, 180, opaque=True), p, "png", opaque),
        ),
        ("icon-192.png", lambda p: save_image(_square(job, 192), p, "png", job.options)),
        ("icon-512.png", lambda p: save_image(_square(job, 512), p, "png", job.options)),
    ]
    written: list[Path] = []
    total = len(steps) + 2 + int(is_vector(job.source))
    for i, (filename, write) in enumerate(steps, 1):
        out = root / filename
        write(out)
        written.append(out)
        progress(i, total)

    bg = "#{:02x}{:02x}{:02x}".format(*job.options.background)
    manifest = {
        "name": job.name,
        "short_name": job.name,
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
        "theme_color": bg,
        "background_color": bg,
        "display": "standalone",
    }
    manifest_path = root / "site.webmanifest"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    written.append(manifest_path)

    svg_line = ""
    if is_vector(job.source) and job.source.suffix.lower() == ".svg":
        svg_path = root / "favicon.svg"
        shutil.copyfile(job.source, svg_path)
        written.append(svg_path)
        svg_line = '<link rel="icon" type="image/svg+xml" href="/favicon.svg">\n'
    snippet = root / "head-snippet.html"
    snippet.write_text(_FAVICON_SNIPPET.format(svg_line=svg_line), encoding="utf-8")
    written.append(snippet)
    progress(total, total)
    return written


def _wallpaper_writer(
    folder: str, sizes: tuple[tuple[int, int], ...]
) -> Callable[[Job, Progress], list[Path]]:
    def write(job: Job, progress: Progress) -> list[Path]:
        root = unique_path(job.out_dir / f"{job.name}-{folder}")
        written: list[Path] = []
        for i, (w, h) in enumerate(sizes, 1):
            out = root / f"{job.name}_{w}x{h}.{job.fmt}"
            save_image(render(job.source, w, h, job.options_at(w, h)), out, job.fmt, job.options)
            written.append(out)
            progress(i, len(sizes))
        return written

    return write


def _squares(sizes: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
    return tuple((s, s) for s in sizes)


PROFILES: tuple[Profile, ...] = (
    Profile(
        "convert",
        "Convert / resize",
        "Convert",
        "One image at the width and height you choose.",
        CONVERT_FORMATS,
        _write_convert,
    ),
    Profile(
        "windows-ico",
        "Windows icon (.ico)",
        "App icons",
        "One .ico holding 16 to 256 px, each size rendered separately.",
        ("ico",),
        _write_ico,
        _squares(WINDOWS_ICO_SIZES),
    ),
    Profile(
        "macos-icns",
        "macOS icon (.icns)",
        "App icons",
        "One .icns holding 16 to 1024 px (16 to 512 pt, 1x and Retina).",
        ("icns",),
        _write_icns,
        _squares(MACOS_ICNS_SIZES),
    ),
    Profile(
        "linux",
        "Linux icon theme",
        "App icons",
        "hicolor/<size>/apps/<name>.png from 16 to 512 px, plus scalable SVG.",
        ("png",),
        _write_linux,
        _squares(LINUX_HICOLOR_SIZES),
    ),
    Profile(
        "android",
        "Android launcher icons",
        "App icons",
        "Adaptive icon layers and XML, legacy and round icons (mdpi-xxxhdpi), Play Store icon.",
        ("png", "webp"),
        _write_android,
        (*((s, s) for _, s in ANDROID_MIPMAPS), (ANDROID_PLAY_STORE, ANDROID_PLAY_STORE)),
    ),
    Profile(
        "ios",
        "iOS / iPadOS app icon",
        "App icons",
        "Xcode AppIcon.appiconset with Contents.json, 20 to 1024 px, opaque.",
        ("png",),
        _write_ios,
        _squares(tuple(sorted({round(pt * sc) for _, pt, sc in IOS_APPICON_SLOTS}))),
        forces_opaque=True,
    ),
    Profile(
        "web",
        "Website favicons",
        "Web",
        "favicon.ico, PNG favicons, apple-touch-icon, manifest icons and HTML snippet.",
        ("png",),
        _write_web,
        _squares((*FAVICON_ICO_SIZES, 180, 192, 512)),
    ),
    Profile(
        "wallpaper-desktop",
        "Desktop wallpapers",
        "Wallpapers",
        "720p to 5K, including 1440p ultrawide.",
        RASTER_FORMATS,
        _wallpaper_writer("wallpapers-desktop", DESKTOP_WALLPAPERS),
        DESKTOP_WALLPAPERS,
    ),
    Profile(
        "wallpaper-phone",
        "Phone wallpapers",
        "Wallpapers",
        "Common iPhone and Android portrait screens.",
        RASTER_FORMATS,
        _wallpaper_writer("wallpapers-phone", PHONE_WALLPAPERS),
        PHONE_WALLPAPERS,
    ),
    Profile(
        "wallpaper-tablet-portrait",
        "Tablet wallpapers (portrait)",
        "Wallpapers",
        "iPad and Android tablet screens, portrait.",
        RASTER_FORMATS,
        _wallpaper_writer("wallpapers-tablet-portrait", TABLET_PORTRAIT_WALLPAPERS),
        TABLET_PORTRAIT_WALLPAPERS,
    ),
    Profile(
        "wallpaper-tablet-landscape",
        "Tablet wallpapers (landscape)",
        "Wallpapers",
        "iPad and Android tablet screens, landscape.",
        RASTER_FORMATS,
        _wallpaper_writer("wallpapers-tablet-landscape", TABLET_LANDSCAPE_WALLPAPERS),
        TABLET_LANDSCAPE_WALLPAPERS,
    ),
)

_BY_ID = {p.id: p for p in PROFILES}


def get_profile(profile_id: str) -> Profile:
    """Look up a profile by id.

    Raises:
        KeyError: with the list of valid ids, if ``profile_id`` is unknown.
    """
    try:
        return _BY_ID[profile_id]
    except KeyError:
        valid = ", ".join(_BY_ID)
        raise KeyError(f"Unknown profile {profile_id!r}. Choose one of: {valid}") from None
