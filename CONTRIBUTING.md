# Contributing

Thanks for helping. Bug reports with the source image attached are the most
useful contribution of all.

## Set up

```bash
git clone https://github.com/RandyNorthrup/pixport.git
cd pixport
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install                  # optional: run the gates on every commit
```

Run the app with `pixport` (or `python -m pixport`), the tests with `pytest`.

## Gates

CI runs exactly these; each one fails the build on findings.

```bash
ruff check .
ruff format --check .
mypy
vulture
bandit -c pyproject.toml -r src
pip-audit --skip-editable
pytest --cov --cov-fail-under=85
```

## Where things live

| Path | What |
|---|---|
| `src/pixport/render.py` | Loads a source and places it on a canvas. No Qt. |
| `src/pixport/profiles.py` | Every export profile: sizes, formats, folder layout. |
| `src/pixport/cli.py` | Command line. |
| `src/pixport/gui/` | Desktop app: window, preview canvas, theme. |
| `packaging/` | PyInstaller spec, app icons, Linux launcher. |
| `tools/screenshots.py` | Regenerates the README screenshots from the real window. |

## Adding a profile

Add an entry to `PROFILES` in `profiles.py` with a writer function. The GUI
menu and the CLI pick it up automatically. Add a test in
`tests/test_profiles.py` that checks every file, size and folder it promises,
then list it in the README's profile table and in `CHANGELOG.md`.

## Tests must be able to fail

A new test should fail without your change. Break the code on purpose, watch
the test go red, then restore it.

## Releasing

1. Bump `__version__` in `src/pixport/__init__.py`.
2. Move the `Unreleased` notes in `CHANGELOG.md` under the new version.
3. Tag `vX.Y.Z` on `main` and push the tag. The release workflow builds,
   self-tests and publishes the binaries.
