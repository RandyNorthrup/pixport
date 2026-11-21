"""Command line interface.

``pixport`` with no arguments opens the desktop app. With an input file it
exports without any window, which suits build scripts and CI::

    pixport logo.svg -p windows-ico -p macos-icns -o build/icons
    pixport photo.png -p convert -f webp --width 800 --height 600
    pixport --list-profiles
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pixport import APP_NAME, __version__
from pixport.profiles import PROFILES, Job, get_profile
from pixport.render import MAX_EDGE, RenderOptions, SourceError, check_source, parse_color

if TYPE_CHECKING:
    from collections.abc import Sequence


def _edge(value: str) -> int:
    number = int(value)
    if not 1 <= number <= MAX_EDGE:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_EDGE}")
    return number


def _zoom(value: str) -> float:
    number = float(value)
    if not 10 <= number <= 100:  # noqa: PLR2004 - percentage bounds stated in --help
        raise argparse.ArgumentTypeError("must be between 10 and 100")
    return number / 100


def _padding(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return number


def _color(value: str) -> tuple[int, int, int]:
    try:
        return parse_color(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser (exposed for tests and docs)."""
    parser = argparse.ArgumentParser(
        prog="pixport",
        description=(
            f"{APP_NAME} {__version__}: export one image to any format, size, screen or "
            "platform. Run with no arguments to open the app."
        ),
    )
    parser.add_argument("inputs", nargs="*", type=Path, metavar="INPUT", help="SVG or image file")
    parser.add_argument(
        "-p",
        "--profile",
        action="append",
        dest="profiles",
        metavar="ID",
        help="export profile; repeat for several (default: convert). See --list-profiles",
    )
    parser.add_argument(
        "-o", "--out", type=Path, default=Path(), help="output folder (default: current folder)"
    )
    parser.add_argument(
        "-f",
        "--format",
        dest="fmt",
        help=(
            "output format, used by every chosen profile that supports it; other profiles "
            "use their first listed format (default: first listed format)"
        ),
    )
    parser.add_argument(
        "--width", type=_edge, default=1024, help="canvas width for 'convert' (default 1024)"
    )
    parser.add_argument(
        "--height", type=_edge, default=1024, help="canvas height for 'convert' (default 1024)"
    )
    parser.add_argument(
        "--padding",
        type=_padding,
        default=0,
        help="empty margin in pixels on every side, at the largest output size; "
        "smaller sizes keep the same proportion (default 0)",
    )
    parser.add_argument(
        "--zoom", type=_zoom, default=1.0, help="artwork size, 10-100 percent of the fit (100)"
    )
    parser.add_argument(
        "--background",
        type=_color,
        metavar="COLOR",
        help="fill the background with a CSS colour such as white or '#0f172a' "
        "(default: transparent)",
    )
    parser.add_argument("--list-profiles", action="store_true", help="list profiles and exit")
    parser.add_argument("-q", "--quiet", action="store_true", help="print nothing on success")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _list_profiles() -> None:
    width = max(len(p.id) for p in PROFILES)
    for p in PROFILES:
        print(f"{p.id:<{width}}  {p.label}  [{', '.join(p.formats)}]")
        print(f"{'':<{width}}  {p.summary}")


def run(args: argparse.Namespace) -> int:
    """Execute a parsed command line and return the exit status."""
    options = RenderOptions(
        padding=args.padding,
        zoom=args.zoom,
        transparent=args.background is None,
        background=args.background or (255, 255, 255),
    )
    try:
        profiles = [get_profile(pid) for pid in (args.profiles or ["convert"])]
        for source in args.inputs:
            check_source(source)
    except (KeyError, SourceError) as exc:
        print(f"error: {exc.args[0]}", file=sys.stderr)
        return 2
    wanted_fmt = (args.fmt or "").lower().replace("jpeg", "jpg")
    if wanted_fmt and not any(wanted_fmt in p.formats for p in profiles):
        print(f"error: no chosen profile writes {args.fmt!r}", file=sys.stderr)
        return 2

    failures = 0
    for source in args.inputs:
        for profile in profiles:
            fmt = wanted_fmt if wanted_fmt in profile.formats else profile.formats[0]
            job = Job(source, args.out, fmt, args.width, args.height, options)
            try:
                written = profile.run(job)
            except (ValueError, OSError) as exc:
                print(f"error: {source.name} -> {profile.id}: {exc}", file=sys.stderr)
                failures += 1
                continue
            if not args.quiet:
                print(f"{source.name} -> {profile.id}: {len(written)} file(s)")
                for path in written:
                    print(f"  {path}")
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``pixport`` command."""
    args = build_parser().parse_args(argv)
    if args.list_profiles:
        _list_profiles()
        return 0
    if not args.inputs:
        from pixport.gui.app import main as gui_main  # noqa: PLC0415 - keep Qt out of CLI runs

        return gui_main()
    return run(args)
