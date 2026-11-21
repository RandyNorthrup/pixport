# PyInstaller spec for the Pixport desktop app.
#
#   pyinstaller packaging/pixport.spec --noconfirm
#
# Windows: dist/Pixport.exe (one portable file)
# macOS:   dist/Pixport.app
# Linux:   dist/pixport/ (folder with the pixport executable)
# ruff: noqa
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "src"))
from pixport import __version__  # noqa: E402

ICONS = ROOT / "packaging" / "icons"
WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"

# Qt modules Pixport never imports. Excluding them roughly halves the bundle.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuickWidgets", "PySide6.QtQuick3D", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSerialPort",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtNetwork", "tkinter", "unittest", "pydoc",
]


def _version_file() -> str | None:
    if not WINDOWS:
        return None
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct,
        VSVersionInfo,
    )

    parts = tuple(int(p) for p in __version__.split(".")) + (0,)
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=parts, prodvers=parts),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "Randy Northrup"),
                StringStruct("FileDescription", "Pixport"),
                StringStruct("FileVersion", __version__),
                StringStruct("InternalName", "Pixport"),
                StringStruct("LegalCopyright", "MIT License"),
                StringStruct("OriginalFilename", "Pixport.exe"),
                StringStruct("ProductName", "Pixport"),
                StringStruct("ProductVersion", __version__),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
    path = Path(workpath) / "version_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(info), encoding="utf-8")
    return str(path)


a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("pixport", includes=["assets/*"]),
    hiddenimports=["resvg_py"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

if WINDOWS:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="Pixport",
        icon=str(ICONS / "pixport.ico"),
        version=_version_file(),
        console=False,
        upx=False,
    )
else:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="pixport",
        icon=str(ICONS / ("pixport.icns" if MACOS else "pixport.ico")),
        console=False,
        upx=False,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="pixport", upx=False)
    if MACOS:
        app = BUNDLE(
            coll,
            name="Pixport.app",
            icon=str(ICONS / "pixport.icns"),
            bundle_identifier="io.github.randynorthrup.pixport",
            version=__version__,
            info_plist={
                "CFBundleDisplayName": "Pixport",
                "CFBundleShortVersionString": __version__,
                "NSHighResolutionCapable": True,
                "LSMinimumSystemVersion": "12.0",
                "CFBundleDocumentTypes": [{
                    "CFBundleTypeName": "Image",
                    "CFBundleTypeRole": "Viewer",
                    "LSItemContentTypes": ["public.svg-image", "public.png", "public.jpeg", "public.image"],
                }],
            },
        )
