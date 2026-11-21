# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.1.0] - 2026-11-21

### Breaking changes

- **Python 3.11 or later is required** (was 3.10, which reached end of life in
  October 2026). Tested on 3.11 to 3.14; release builds use Python 3.14.

### Added

- **Android adaptive icons.** The `android` profile now also writes the
  `ic_launcher_foreground` and `ic_launcher_monochrome` layers for every density
  (artwork inside the 66 dp safe zone), `mipmap-anydpi-v26/ic_launcher.xml` and
  `ic_launcher_round.xml`, `values/ic_launcher_background.xml` with the background
  colour, and a round legacy `ic_launcher_round` icon. The monochrome layer gives
  Android 13 themed icons. One export now writes 24 files instead of 6.
- **16 px image in macOS `.icns`.** Pixport writes the container itself with every
  element `iconutil` produces, 16 to 1024 px, instead of Pillow's writer, which had
  no 16 px slot.

### Changed

- **Previews render off the UI thread.** Dragging a slider over a heavy SVG no
  longer stalls the window; only the newest pending preview is rendered.
- **Code signing is out of scope for good.** Docs say so instead of "not yet".

## [2.0.1] - 2026-11-21

### Fixed

- **The window's size is remembered.** 2.0.0 restored the saved size and then
  immediately replaced it with the default, so only the position survived a restart.
- **The first window fits small screens.** The default 1180 × 760 window was larger
  than a 1024 × 768 display; it now takes at most 90 % of the screen.
- **macOS first-launch instructions** in the README now cover macOS 15 and later,
  where right-click → Open no longer bypasses Gatekeeper for unsigned apps.

### Changed

- CI and release workflows use the current major versions of `actions/checkout`,
  `actions/setup-python`, `actions/upload-artifact`, `actions/download-artifact` and
  `gitleaks/gitleaks-action` (Node 24 runtimes). With `download-artifact` v8 the
  publish job verifies each build artifact's digest and fails on a mismatch.

## [2.0.0] - 2026-11-21

SVG-PNG-Tool is now **Pixport**: renamed, rebuilt as an installable package with a
command line, and released as binaries for Windows, macOS and Linux.

### Breaking changes

- **New name and commands.** Run `pixport` (or `pixport-gui`, or `python -m pixport`)
  instead of `python svg_converter.py`. Install with
  `pipx install git+https://github.com/RandyNorthrup/pixport.git` or download a release.
- **SVG renderer is now resvg** (via `resvg-py`) instead of CairoSVG. No Cairo or GTK
  install is needed on any system. resvg supports more of SVG than CairoSVG, so some
  files render differently, usually more correctly.
- **Python 3.10 or later** is required (was 3.9).
- **Output names and folders changed** so the results drop straight into each platform:

  | Profile | 1.x wrote | 2.0 writes |
  |---|---|---|
  | Custom export | `custom/name_<w>x<h>.<ext>` | `name_<w>x<h>.<ext>` |
  | Windows icon | `windows/icon.ico` | `name.ico` |
  | macOS icon | `macos/icon.icns` | `name.icns` |
  | Linux | `linux/name/name_<n>x<n>.png` | `name-linux/hicolor/<n>x<n>/apps/name.png` |
  | Android | `android/name/name_<n>x<n>.png` | `name-android/mipmap-*/ic_launcher.png` + `playstore-icon.png` |
  | iOS | `ios/name/name_<n>x<n>.png` | `name-ios/AppIcon.appiconset/Icon-<n>.png` + `Contents.json` |
  | Wallpapers | `wallpapers/<kind>/name/…` | `name-wallpapers-<kind>/…` |

- **Profiles that need it no longer offer JPG and BMP.** Linux, Android and iOS icon
  sets were offered as JPG or BMP, which those platforms do not accept. Linux and iOS
  write PNG; Android writes PNG or WEBP.
- **Size lists were updated** for current devices (see below). The macOS `.icns` no
  longer claims a 16 px image; see Fixed.

### Added

- **Command line** with the same profiles as the app: several inputs and profiles in
  one run, `--width`, `--height`, `--padding`, `--zoom`, `--background`, `--format`,
  `--list-profiles`, `--quiet`, and exit codes 0 / 1 / 2.
- **Website favicons profile**: `favicon.ico`, PNG favicons, `apple-touch-icon.png`,
  192 and 512 px manifest icons, `site.webmanifest`, `favicon.svg` for SVG sources,
  and a `head-snippet.html`.
- **iOS `AppIcon.appiconset`** with `Contents.json` covering every iPhone, iPad and
  App Store slot (20 to 1024 px, including 83.5 pt iPad Pro), always opaque as App
  Store Connect requires.
- **Android `mipmap-mdpi` to `mipmap-xxxhdpi`** layout and a 512 px Play Store icon.
- **Linux `hicolor` theme layout**, plus `scalable/apps/name.svg` for SVG sources.
- **Formats:** WEBP and TIFF output; JPG, WEBP, BMP, GIF, TIFF, ICO and SVGZ input.
- **More sizes:** Windows `.ico` adds 20, 40 and 96 px. Desktop wallpapers add 1366×768,
  3440×1440 and 5120×2880. Phone wallpapers add 1080×2400, 1179×2556, 1290×2796 and
  1440×3200. Tablet wallpapers add 1640×2360 and 2048×2732.
- **Redesigned window**: light and dark themes that follow the system, a preview on a
  transparency checkerboard that fills the window and stays sharp on high-DPI screens,
  drag and drop, aspect-ratio lock, a list of every size the profile writes, a hint
  explaining when the background colour applies, File and Help menus, and keyboard
  shortcuts (Ctrl+O, Ctrl+E).
- **Exports run in the background** with a progress bar and Cancel, then offer
  **Show folder**.
- **Settings are remembered** between launches: profile, format, size, padding,
  artwork size, background, folders and window position.
- **Release binaries** built by GitHub Actions for Windows x64, macOS Apple silicon,
  macOS Intel and Linux x64, each verified by running the packaged app's
  `--self-test` before publishing, with SHA-256 checksums.
- **Linux installer script** that adds a menu entry and icons for the current user.
- Test suite grown from 12 to 110 tests across rendering, every profile's files and
  folders, the command line and the window; CI runs it on Windows, macOS and Linux
  with Python 3.10 and 3.13.

### Fixed

- **Padding no longer swallows small icons.** 1.x applied the same absolute padding at
  every size, so 64 px of padding left a 16 px icon with a 1 px artwork. Padding is
  now set at the largest output size and scaled for each smaller one.
- **Small icon sizes are sharp.** `.ico` and `.icns` frames are each rendered at their
  own size instead of being shrunk from one 256 px or 1024 px image.
- **The preview matches the export.** For PNG sources the preview stretched the image
  to the canvas and ignored padding, zoom and background; it now uses the export code.
  It also shows formats without transparency (JPG, BMP, PDF, iOS) on their background.
- **The size boxes no longer mislead.** Width and height stayed editable for icon and
  wallpaper profiles, changed the preview, and were then ignored by the export. They
  now appear only for Convert / resize.
- **The app starts without Cairo.** 1.x exited on systems without the Cairo library,
  which included every stock Windows install.
- **The macOS `.icns` contents are described correctly.** Pillow's ICNS writer has no
  16 px slot; 2.0 renders the 32 to 1024 px images it does store and the docs say so.
- **The window no longer freezes** during long exports.
- **A broken or unsupported file shows a message** instead of an error inside the
  preview, and a file that is not an image is refused when opened.

### Removed

- The `iconutil` fallback for `.icns`. Pillow writes `.icns` on every system, so the
  macOS-only subprocess path was dead code in practice.
- `requirements.txt` and the hand-written `VERSION.txt`; dependencies live in
  `pyproject.toml` and the Windows version resource is generated from the package
  version at build time.

## 1.0.0 - 2025-09-26 (SVG-PNG-Tool, untagged)

The last SVG-PNG-Tool release: a single-file PySide6 app rendering SVG with CairoSVG,
with profiles for custom export, Windows `.ico`, macOS `.icns`, Linux, Android and iOS
PNG sets, and desktop, phone and tablet wallpapers. A later quality pass added strict
lint and type configuration, 12 tests, and fixes for three PNG-input defects (zoom and
padding ignored, opaque background composited onto black, invalid `.iconset` names) in July 2026.

[Unreleased]: https://github.com/RandyNorthrup/pixport/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/RandyNorthrup/pixport/releases/tag/v2.1.0
[2.0.1]: https://github.com/RandyNorthrup/pixport/releases/tag/v2.0.1
[2.0.0]: https://github.com/RandyNorthrup/pixport/releases/tag/v2.0.0
