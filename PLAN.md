# PLAN

Design decisions, quality baseline and known limitations for Pixport. Updated for
2.1.1 (2026-11-21).

## Quality gates

All run in CI (`.github/workflows/ci.yml`) and fail the build on findings.

| Gate | Command | State at 2.0.0 |
|---|---|---|
| Lint | `ruff check .` (`select = ["ALL"]`) | 0 findings |
| Format | `ruff format --check .` | clean |
| Types | `mypy` (strict, PySide6's own stubs) | 0 errors, no blanket ignores |
| Dead code | `vulture` (min confidence 60) | 0; Qt event overrides allowlisted |
| Security | `bandit -c pyproject.toml -r src` | 0 findings |
| Dependencies | `pip-audit --skip-editable` | no known vulnerabilities |
| Secrets | gitleaks over full history | clean |
| Tests | `pytest --cov --cov-fail-under=85` | 119 passing, 91 % line coverage, on Windows, macOS and Linux × Python 3.11 and 3.14 |
| Packaged build | `release.yml`: PyInstaller build, then the app's `--self-test` | runs on every PR touching code or packaging, on all four targets |

Key behaviours each have a test that was checked to fail when the behaviour is
broken: padding, background colour, per-size ICO frames, iOS opacity, never
overwriting, CLI format fallback, preview opacity, aspect lock, padding scaling, saved window size,
preview rendered off the UI thread.

## Decisions

**resvg instead of CairoSVG.** CairoSVG needs the Cairo C library, which stock
Windows does not have; 1.x exited at start-up there. `resvg-py` ships resvg inside
its wheels for Windows, macOS and Linux (x64 and ARM), renders more of the SVG
specification, and needs nothing installed. Trade-off: one renderer from a small
project; see Risks.

**Qt-free core.** `render.py` and `profiles.py` import no Qt. The GUI, the CLI and
the tests share one rendering path, so the preview cannot disagree with the export,
and core tests run without a display.

**Profiles are data.** One `PROFILES` table drives the GUI menu, the CLI's
`--profile` choices and `--list-profiles`. 1.x had every export written twice (SVG
and PNG input) inside a 119-statement method; that duplication is gone.

**Padding is set at the largest output size and scaled.** A single absolute margin
cannot be right for both 16 px and 1024 px; proportional scaling matches what the
preview shows.

**Never overwrite.** Single files get `_1`, `_2` suffixes and folder exports get a
new folder. Re-exporting is common; losing hand-edited output is worse than an extra
folder.

**Formats a platform rejects are not offered.** No JPG Android launcher icons, no
transparent iOS icons, Play Store icon always PNG.

**Binary entry point is the GUI.** The packaged apps open the window (and a file
passed to them). The command line comes with the pip install, where a console is
guaranteed; a windowed Windows executable has no stdout.

**`.icns` is written by Pixport, not Pillow.** Pillow's writer has no 16 px element.
The container is simple (a header plus typed PNG elements, the set `iconutil`
writes), so `profiles.icns_bytes` builds it directly and a test checks the layout.

**Previews render on Qt's thread pool.** One render runs at a time and only the
newest request waits behind it, so dragging a slider over a heavy SVG never queues
stale work or blocks the window.

**Android adaptive icons are derived from the one source.** The foreground layer
fits the artwork into the square inscribed in the 66 dp safe circle of the 108 dp
layer, so no launcher mask clips its corners; the background is
the chosen colour, and the monochrome layer reuses the foreground's alpha.

**`--self-test` in the shipped app.** Proves a frozen build can render SVG, write
every format and construct its window on each OS before a release is published.
Writes only to a temporary folder.

## Known limitations

- **Unsigned binaries, by decision.** The project will not code-sign. Windows
  SmartScreen and macOS Gatekeeper warn on first launch; the README explains how to
  open the app, and every release lists SHA-256 checksums built by CI from the tag.
- **Not on PyPI yet.** Install from git. Publishing needs a trusted publisher set up
  on pypi.org. Deferred by choice.
- **PDF output is raster.** resvg renders to pixels; vector PDF would need a second
  renderer.
- **Linux bundle targets glibc 2.35+** (built on Ubuntu 22.04).

## Risks

- **`resvg-py` is maintained by one person.** If it stalls, the fallbacks are the
  `resvg` CLI as a subprocess or `skia-python`. Only `render._svg_png` would change.
- **PySide6 minor releases occasionally change stubs**, which can fail strict mypy
  on upgrade. Dependabot PRs surface this before it reaches `main`.

## Next

1. PyPI release via trusted publishing.
2. Batch mode in the app (several sources in one export; the CLI already does it).
3. Separate foreground and background artwork for Android adaptive icons.
