# Security policy

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Report privately through
[GitHub security advisories](https://github.com/RandyNorthrup/pixport/security/advisories/new).
Please do not open a public issue. You should get a reply within a week.

## Scope

Pixport runs locally and makes no network requests. The realistic risk is a
crafted input file: SVG is parsed by [resvg](https://github.com/linebender/resvg)
and raster formats by [Pillow](https://python-pillow.org/), with Pillow's
decompression-bomb limit left on. Reports of inputs that crash or hang either
library through Pixport are welcome; they are usually forwarded upstream as well.

Release binaries are built by GitHub Actions from the tagged commit and listed
with SHA-256 checksums in `SHA256SUMS.txt` on each release. They are not
code-signed, so Windows SmartScreen and macOS Gatekeeper warn on first launch.
