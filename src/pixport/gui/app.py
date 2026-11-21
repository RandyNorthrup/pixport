"""Pixport main window."""

from __future__ import annotations

import sys
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from PySide6.QtCore import (
    QByteArray,
    QSettings,
    QSize,
    Qt,
    QThread,
    QThreadPool,
    QTimer,
    QUrl,
    Slot,
)
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QImage, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pixport import APP_ID, APP_NAME, __version__
from pixport.gui.theme import apply_theme, system_theme
from pixport.gui.widgets import (
    ExportWorker,
    PreviewCanvas,
    PreviewRequest,
    PreviewSignals,
    PreviewTask,
)
from pixport.profiles import OPAQUE_FORMATS, PROFILES, Job, Profile, get_profile
from pixport.render import (
    MAX_EDGE,
    RGB,
    SUPPORTED_SUFFIXES,
    RenderOptions,
    SourceError,
    check_source,
    is_vector,
    source_size,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

REPO_URL = "https://github.com/RandyNorthrup/pixport"
PREVIEW_DEBOUNCE_MS = 120
SIDEBAR_WIDTH = 340
DEFAULT_EDGE = 1024
DEFAULT_WINDOW = QSize(1180, 760)
#: Largest share of the screen a first-run window may take.
SCREEN_FRACTION = 0.9
MAX_PADDING = 4096
MAX_LISTED_SIZES = 8

_W = TypeVar("_W", bound=QWidget)


def _hex(rgb: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def app_icon() -> QIcon:
    """The Pixport icon bundled with the package."""
    icon = QIcon()
    folder = resources.files("pixport") / "assets"
    for size in (32, 64, 128, 256, 512):
        ref = folder / f"pixport-{size}.png"
        if ref.is_file():
            with resources.as_file(ref) as path:
                icon.addFile(str(path), QSize(size, size))
    return icon


def default_window_size(available: QSize) -> QSize:
    """First-run window size: the design size, shrunk to fit small screens."""
    return QSize(
        min(DEFAULT_WINDOW.width(), int(available.width() * SCREEN_FRACTION)),
        min(DEFAULT_WINDOW.height(), int(available.height() * SCREEN_FRACTION)),
    )


def _named(widget: _W, name: str) -> _W:
    """Set the object name the stylesheet selects on, and return the widget."""
    widget.setObjectName(name)
    return widget


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("section")
    return label


class MainWindow(QMainWindow):
    """Preview on the left, settings on the right, one Export button."""

    def __init__(self, settings: QSettings | None = None) -> None:
        """Build the window and restore the last session's settings."""
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.settings = settings or QSettings(APP_NAME, APP_NAME)
        self.source: Path | None = None
        self.source_dims: tuple[int, int] | None = None
        self.background: RGB = (255, 255, 255)
        self._thread: QThread | None = None
        self._worker: ExportWorker | None = None
        self._last_output: Path | None = None
        self._syncing_size = False

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.timeout.connect(self.refresh_preview)
        # One render in flight at a time; while it runs only the newest request waits.
        self._preview_signals = PreviewSignals(self)
        self._preview_signals.done.connect(self._on_preview_done)
        self._preview_seq = 0
        self._preview_shown = 0
        self._preview_busy = False
        self._preview_pending: PreviewTask | None = None

        self._build_ui()
        self._build_menu()
        self._wire()
        self._restore()
        self.apply_system_theme()

    # ── construction ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = _named(QWidget(), "root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        left = QVBoxLayout()
        left.setContentsMargins(12, 12, 12, 6)
        self.canvas = PreviewCanvas()
        self.info = _named(QLabel(), "info")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        left.addWidget(self.canvas, 1)
        left.addWidget(self.info)
        layout.addLayout(left, 1)

        layout.addWidget(self._build_sidebar())
        self.setCentralWidget(root)

        self.status_text = QLabel()
        self.show_folder_btn = _named(QPushButton("Show folder"), "link")
        self.show_folder_btn.setVisible(False)
        self.statusBar().addWidget(self.status_text, 1)
        self.statusBar().addPermanentWidget(self.show_folder_btn)

    def _build_sidebar(self) -> QWidget:
        panel = _named(QWidget(), "sidebar")
        panel.setFixedWidth(SIDEBAR_WIDTH)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("sidebar")
        col = QVBoxLayout(body)
        col.setContentsMargins(18, 16, 18, 12)
        col.setSpacing(6)

        brand_row = QHBoxLayout()
        brand_icon = QLabel()
        brand_icon.setPixmap(app_icon().pixmap(28, 28))
        brand = _named(QLabel(APP_NAME), "brand")
        version = _named(QLabel(f"v{__version__}"), "version")
        brand_row.addWidget(brand_icon)
        brand_row.addWidget(brand)
        brand_row.addStretch(1)
        brand_row.addWidget(version)
        col.addLayout(brand_row)

        # Source
        col.addWidget(_section("Source"))
        src_row = QHBoxLayout()
        self.source_label = _named(QLabel("No file open"), "muted")
        self.source_label.setMinimumWidth(0)
        self.open_btn = QPushButton("Open…")
        self.open_btn.setToolTip("Open an SVG or image (Ctrl+O)")
        src_row.addWidget(self.source_label, 1)
        src_row.addWidget(self.open_btn)
        col.addLayout(src_row)
        self.source_meta = _named(QLabel(""), "hint")
        col.addWidget(self.source_meta)

        # Output
        col.addWidget(_section("Output"))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.profile_combo = QComboBox()
        self.profile_combo.setAccessibleName("Export profile")
        last_group = ""
        for profile in PROFILES:
            if profile.group != last_group:
                if last_group:
                    self.profile_combo.insertSeparator(self.profile_combo.count())
                last_group = profile.group
            self.profile_combo.addItem(profile.label, profile.id)
        self.format_combo = QComboBox()
        self.format_combo.setAccessibleName("Output format")
        form.addRow("Profile", self.profile_combo)
        self.summary = _named(QLabel(), "summary")
        self.summary.setWordWrap(True)
        form.addRow(self.summary)
        form.addRow("Format", self.format_combo)

        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        for spin, name in ((self.width_spin, "Width"), (self.height_spin, "Height")):
            spin.setRange(1, MAX_EDGE)
            spin.setValue(DEFAULT_EDGE)
            spin.setSuffix(" px")
            spin.setAccessibleName(f"{name} in pixels")
            spin.setKeyboardTracking(False)
            # The 16384 range plus suffix makes Qt's size hint wider than the sidebar.
            spin.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.lock_btn = QPushButton("🔗")
        self.lock_btn.setCheckable(True)
        self.lock_btn.setChecked(True)
        self.lock_btn.setFixedWidth(36)
        self.lock_btn.setToolTip("Keep the source's aspect ratio")
        self.lock_btn.setAccessibleName("Lock aspect ratio")
        self.size_row = QWidget()
        size_layout = QHBoxLayout(self.size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.addWidget(self.width_spin, 1)
        size_layout.addWidget(QLabel("×"))  # noqa: RUF001 - multiplication sign is display text
        size_layout.addWidget(self.height_spin, 1)
        size_layout.addWidget(self.lock_btn)
        self.size_label = QLabel("Size")
        form.addRow(self.size_label, self.size_row)
        col.addLayout(form)

        # Layout
        col.addWidget(_section("Layout"))
        layout_form = QFormLayout()
        layout_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.padding_spin = QSpinBox()
        self.padding_spin.setRange(0, MAX_PADDING)
        self.padding_spin.setSuffix(" px")
        self.padding_spin.setAccessibleName("Padding in pixels")
        self.padding_spin.setToolTip("Empty margin on every side, at the largest output size")
        layout_form.addRow("Padding", self.padding_spin)
        zoom_row = QHBoxLayout()
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 100)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setAccessibleName("Artwork size percent")
        self.zoom_value = QLabel("100%")
        self.zoom_value.setMinimumWidth(40)
        self.zoom_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        zoom_row.addWidget(self.zoom_slider, 1)
        zoom_row.addWidget(self.zoom_value)
        layout_form.addRow("Artwork", zoom_row)
        col.addLayout(layout_form)

        # Background
        col.addWidget(_section("Background"))
        self.transparent_chk = QCheckBox("Transparent")
        self.transparent_chk.setChecked(True)
        bg_row = QHBoxLayout()
        self.color_btn = QPushButton()
        self.color_btn.setAccessibleName("Background colour")
        self.color_btn.setToolTip("Background colour")
        bg_row.addWidget(self.transparent_chk, 1)
        bg_row.addWidget(self.color_btn)
        col.addLayout(bg_row)
        self.bg_hint = _named(QLabel(), "hint")
        self.bg_hint.setWordWrap(True)
        col.addWidget(self.bg_hint)

        col.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        footer = QVBoxLayout()
        footer.setContentsMargins(18, 8, 18, 16)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.export_btn = _named(QPushButton("Export…"), "primary")
        self.export_btn.setEnabled(False)
        self.export_btn.setToolTip("Choose a folder and export (Ctrl+E)")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        footer.addWidget(self.progress)
        footer.addWidget(self.export_btn)
        footer.addWidget(self.cancel_btn)
        outer.addLayout(footer)
        return panel

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.open_action = QAction(
            "&Open…", self, shortcut=QKeySequence(QKeySequence.StandardKey.Open)
        )
        self.export_action = QAction("&Export…", self, shortcut=QKeySequence("Ctrl+E"))
        self.export_action.setEnabled(False)
        quit_action = QAction("&Quit", self, shortcut=QKeySequence(QKeySequence.StandardKey.Quit))
        quit_action.triggered.connect(self.close)
        file_menu.addActions([self.open_action, self.export_action])
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("&Help")
        site = QAction("Pixport on &GitHub", self)
        site.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        about = QAction(f"&About {APP_NAME}", self)
        about.triggered.connect(self.show_about)
        help_menu.addActions([site, about])

    def _wire(self) -> None:
        self.open_btn.clicked.connect(self.choose_source)
        self.open_action.triggered.connect(self.choose_source)
        self.canvas.open_requested.connect(self.choose_source)
        self.canvas.file_dropped.connect(self.load_source)
        self.canvas.resized.connect(self.schedule_preview)
        self.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        self.format_combo.currentIndexChanged.connect(self.on_settings_changed)
        self.width_spin.valueChanged.connect(self.on_width_changed)
        self.height_spin.valueChanged.connect(self.on_height_changed)
        self.lock_btn.toggled.connect(self.on_lock_toggled)
        self.padding_spin.valueChanged.connect(self.on_settings_changed)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        self.transparent_chk.toggled.connect(self.on_settings_changed)
        self.color_btn.clicked.connect(self.choose_background)
        self.export_btn.clicked.connect(self.export)
        self.export_action.triggered.connect(self.export)
        self.cancel_btn.clicked.connect(self.cancel_export)
        self.show_folder_btn.clicked.connect(self.show_output_folder)
        QApplication.styleHints().colorSchemeChanged.connect(self.apply_system_theme)

    # ── settings persistence ────────────────────────────────────────────────

    def _restore(self) -> None:
        s = self.settings
        profile_id = str(s.value("profile", "convert"))
        index = self.profile_combo.findData(profile_id)
        self.profile_combo.setCurrentIndex(max(0, index))
        self.on_profile_changed()
        fmt = str(s.value("format", ""))
        if fmt and self.format_combo.findText(fmt.upper()) >= 0:
            self.format_combo.setCurrentText(fmt.upper())
        self._syncing_size = True
        self.width_spin.setValue(self._int_setting("width", DEFAULT_EDGE))
        self.height_spin.setValue(self._int_setting("height", DEFAULT_EDGE))
        self._syncing_size = False
        self.lock_btn.setChecked(str(s.value("lock_aspect", "true")) == "true")
        self.padding_spin.setValue(self._int_setting("padding", 0))
        self.zoom_slider.setValue(self._int_setting("zoom", 100))
        self.transparent_chk.setChecked(str(s.value("transparent", "true")) == "true")
        colour = QColor(str(s.value("background", "#ffffff")))
        if colour.isValid():
            self.background = (colour.red(), colour.green(), colour.blue())
        geometry = s.value("geometry")
        # Native backends return QByteArray; accept bytes too in case a PySide6
        # version or settings format converts it.
        restorable = isinstance(geometry, (QByteArray, bytes, bytearray))
        if not (restorable and self.restoreGeometry(QByteArray(geometry))):
            screen = QApplication.primaryScreen()
            if screen is not None:
                self.resize(default_window_size(screen.availableGeometry().size()))
        self._update_background_ui()

    def _int_setting(self, key: str, default: int) -> int:
        try:
            return int(str(self.settings.value(key, default)))
        except ValueError:
            return default

    def save_settings(self) -> None:
        """Persist the current settings for the next launch."""
        s = self.settings
        s.setValue("profile", self.current_profile().id)
        s.setValue("format", self.format_combo.currentText().lower())
        s.setValue("width", self.width_spin.value())
        s.setValue("height", self.height_spin.value())
        s.setValue("lock_aspect", "true" if self.lock_btn.isChecked() else "false")
        s.setValue("padding", self.padding_spin.value())
        s.setValue("zoom", self.zoom_slider.value())
        s.setValue("transparent", "true" if self.transparent_chk.isChecked() else "false")
        s.setValue("background", _hex(self.background))
        s.setValue("geometry", self.saveGeometry())

    def closeEvent(self, event: object) -> None:
        """Save settings and stop a running export before closing."""
        self.save_settings()
        if self._worker is not None:
            self._worker.cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        super().closeEvent(event)  # type: ignore[arg-type]

    # ── state helpers ───────────────────────────────────────────────────────

    def current_profile(self) -> Profile:
        """The profile selected in the menu."""
        return get_profile(str(self.profile_combo.currentData()))

    def current_format(self) -> str:
        """The output format selected in the menu, lower case."""
        return self.format_combo.currentText().lower()

    def render_options(self) -> RenderOptions:
        """Options exactly as the export will use them, including forced opacity."""
        opts = RenderOptions(
            padding=self.padding_spin.value(),
            zoom=self.zoom_slider.value() / 100,
            transparent=self.transparent_chk.isChecked(),
            background=self.background,
        )
        if self.current_profile().forces_opaque or self.current_format() in OPAQUE_FORMATS:
            return opts.opaque()
        return opts

    def build_job(self, out_dir: Path) -> Job:
        """The export request for the current settings."""
        if self.source is None:
            raise SourceError("No file open")
        return Job(
            self.source,
            out_dir,
            self.current_format(),
            self.width_spin.value(),
            self.height_spin.value(),
            self.render_options(),
        )

    def _set_status(self, text: str, *, folder: Path | None = None) -> None:
        self.status_text.setText(text)
        self._last_output = folder
        self.show_folder_btn.setVisible(folder is not None)

    # ── slots ────────────────────────────────────────────────────────────────

    @Slot()
    def apply_system_theme(self) -> None:
        """Re-theme when the OS switches between light and dark."""
        theme = system_theme()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, theme)
        self.canvas.set_theme(theme)
        self._update_background_ui()

    @Slot()
    def choose_source(self) -> None:
        """Ask for a file and open it."""
        patterns = " ".join(f"*{suffix}" for suffix in sorted(SUPPORTED_SUFFIXES))
        start = str(self.settings.value("open_dir", ""))
        path, _ = QFileDialog.getOpenFileName(
            self, "Open image", start, f"Images ({patterns});;All files (*)"
        )
        if path:
            self.load_source(Path(path))

    @Slot(Path)
    def load_source(self, path: Path) -> bool:
        """Open ``path`` as the source. Returns False and explains if it cannot."""
        try:
            check_source(path)
            dims = source_size(path)
        except SourceError as exc:
            QMessageBox.warning(self, "Cannot open file", str(exc))
            return False
        self.source = path
        self.source_dims = dims
        self.settings.setValue("open_dir", str(path.parent))
        metrics = self.source_label.fontMetrics()
        self.source_label.setText(
            metrics.elidedText(path.name, Qt.TextElideMode.ElideMiddle, SIDEBAR_WIDTH - 130)
        )
        self.source_label.setToolTip(str(path))
        self.source_label.setObjectName("")
        self.source_label.style().unpolish(self.source_label)
        self.source_label.style().polish(self.source_label)
        kind = "SVG" if is_vector(path) else path.suffix.lstrip(".").upper()
        self.source_meta.setText(f"{kind} · {dims[0]} × {dims[1]} px")  # noqa: RUF001
        self.setWindowTitle(f"{path.name} · {APP_NAME}")
        self.export_btn.setEnabled(True)
        self.export_action.setEnabled(True)
        if self.lock_btn.isChecked():
            self._sync_height_from_width()
        self._set_status(f"Opened {path.name}")
        self.refresh_preview()
        return True

    @Slot()
    def on_profile_changed(self) -> None:
        """Swap the format list and size controls for the selected profile."""
        profile = self.current_profile()
        previous = self.format_combo.currentText()
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        self.format_combo.addItems([f.upper() for f in profile.formats])
        if self.format_combo.findText(previous) >= 0:
            self.format_combo.setCurrentText(previous)
        self.format_combo.blockSignals(False)
        self.format_combo.setEnabled(len(profile.formats) > 1)

        self.summary.setText(profile.summary)
        self.size_label.setVisible(profile.uses_custom_size)
        self.size_row.setVisible(profile.uses_custom_size)
        self.on_settings_changed()

    @Slot()
    def on_settings_changed(self) -> None:
        """Any control changed: refresh hints and schedule a new preview."""
        self._update_background_ui()
        self._update_info()
        self.schedule_preview()

    @Slot(int)
    def on_zoom_changed(self, value: int) -> None:
        """Update the zoom read-out."""
        self.zoom_value.setText(f"{value}%")
        self.on_settings_changed()

    def _aspect(self) -> float | None:
        if not self.source_dims:
            return None
        w, h = self.source_dims
        return h / w if w else None

    def _sync_height_from_width(self) -> None:
        aspect = self._aspect()
        if aspect is None:
            return
        self._syncing_size = True
        self.height_spin.setValue(max(1, min(MAX_EDGE, round(self.width_spin.value() * aspect))))
        self._syncing_size = False

    @Slot(int)
    def on_width_changed(self, value: int) -> None:
        """Keep the aspect ratio when locked."""
        if not self._syncing_size and self.lock_btn.isChecked():
            self._sync_height_from_width()
        self.on_settings_changed()

    @Slot(int)
    def on_height_changed(self, value: int) -> None:
        """Keep the aspect ratio when locked."""
        aspect = self._aspect()
        if not self._syncing_size and self.lock_btn.isChecked() and aspect:
            self._syncing_size = True
            self.width_spin.setValue(max(1, min(MAX_EDGE, round(value / aspect))))
            self._syncing_size = False
        self.on_settings_changed()

    @Slot(bool)
    def on_lock_toggled(self, locked: bool) -> None:
        """Re-apply the source ratio when the lock is switched on."""
        if locked:
            self._sync_height_from_width()
        self.on_settings_changed()

    @Slot()
    def choose_background(self) -> None:
        """Pick the background colour."""
        colour = QColorDialog.getColor(QColor(_hex(self.background)), self, "Background colour")
        if colour.isValid():
            self.background = (colour.red(), colour.green(), colour.blue())
            self.on_settings_changed()

    def _update_background_ui(self) -> None:
        hex_colour = _hex(self.background)
        text = "#000000" if sum(self.background) > 382 else "#ffffff"  # noqa: PLR2004 - mid grey
        self.color_btn.setText(hex_colour)
        self.color_btn.setStyleSheet(
            f"QPushButton {{ background: {hex_colour}; color: {text}; min-width: 84px; }}"
        )
        profile = self.current_profile()
        fmt = self.current_format()
        if profile.forces_opaque:
            hint = "iOS app icons cannot be transparent, so this colour fills the background."
        elif fmt in OPAQUE_FORMATS:
            hint = f"{fmt.upper()} has no transparency, so this colour fills the background."
        elif self.transparent_chk.isChecked():
            hint = "Colour is used only by formats without transparency."
        else:
            hint = "This colour fills the background."
        if profile.id == "web" and self.transparent_chk.isChecked():
            hint += " apple-touch-icon is always filled with it."
        self.bg_hint.setText(hint)

    def _update_info(self) -> None:
        profile = self.current_profile()
        fmt = self.current_format().upper()
        if profile.uses_custom_size:
            w, h = self.width_spin.value(), self.height_spin.value()
            text = f"Exports 1 {fmt} at {w} × {h} px"  # noqa: RUF001
        else:
            labels = [f"{w}" if w == h else f"{w}×{h}" for w, h in profile.sizes]  # noqa: RUF001
            shown = ", ".join(labels[:MAX_LISTED_SIZES])
            more = (
                f" and {len(labels) - MAX_LISTED_SIZES} more"
                if len(labels) > MAX_LISTED_SIZES
                else ""
            )
            text = f"{profile.label}: {len(labels)} sizes ({shown}{more}) · {fmt}"
        pw, ph = profile.preview_size(self.width_spin.value(), self.height_spin.value())
        self.info.setText(f"{text}   ·   preview shows {pw} × {ph} px")  # noqa: RUF001

    @Slot()
    def schedule_preview(self) -> None:
        """Re-render shortly, so dragging a slider does not queue a render per step."""
        self._preview_timer.start()

    @Slot()
    def refresh_preview(self) -> None:
        """Ask for a new preview; it is rendered on a pool thread."""
        if self.source is None:
            self.canvas.set_message("Drop an SVG or image here\nor click to open")
            return
        profile = self.current_profile()
        canvas = profile.preview_size(self.width_spin.value(), self.height_spin.value())
        self._preview_seq += 1
        request = PreviewRequest(
            self._preview_seq,
            self.source,
            canvas,
            self.render_options(),
            self.canvas.available_pixels(),
        )
        task = PreviewTask(request, self._preview_signals)
        if self._preview_busy:
            self._preview_pending = task
            return
        self._start_preview(task)

    def _start_preview(self, task: PreviewTask) -> None:
        self._preview_busy = True
        QThreadPool.globalInstance().start(task)

    @property
    def preview_idle(self) -> bool:
        """True when no preview render is running or waiting."""
        return not self._preview_busy and self._preview_pending is None

    @Slot(int, object, str)
    def _on_preview_done(self, seq: int, image: QImage | None, error: str) -> None:
        self._preview_busy = False
        if self._preview_pending is not None:
            task, self._preview_pending = self._preview_pending, None
            self._start_preview(task)
        if seq < self._preview_shown or self.source is None:
            return
        self._preview_shown = seq
        if image is None:
            self.canvas.set_message(f"Cannot preview this file\n\n{error}")
            return
        image.setDevicePixelRatio(self.canvas.devicePixelRatioF())
        self.canvas.set_image(image)

    @Slot()
    def export(self) -> None:
        """Ask for a folder and export in the background."""
        if self.source is None or self._thread is not None:
            return
        start = str(self.settings.value("out_dir", str(self.source.parent)))
        folder = QFileDialog.getExistingDirectory(self, "Export to folder", start)
        if not folder:
            return
        self.settings.setValue("out_dir", folder)
        self.start_export(Path(folder))

    def start_export(self, out_dir: Path) -> None:
        """Run the export into ``out_dir`` on a worker thread."""
        profile = self.current_profile()
        self._worker = ExportWorker(profile, self.build_job(out_dir))
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progressed.connect(self._on_progress)
        self._worker.succeeded.connect(lambda paths: self._on_success(out_dir, paths))
        self._worker.failed.connect(self._on_failure)
        self._worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)
        self._set_busy(True)
        self._set_status(f"Exporting {profile.label}…")
        self._thread.start()

    def _set_busy(self, busy: bool) -> None:
        self.export_btn.setVisible(not busy)
        self.cancel_btn.setVisible(busy)
        self.cancel_btn.setEnabled(busy)
        self.progress.setVisible(busy)
        self.progress.setRange(0, 0)
        self.export_action.setEnabled(not busy and self.source is not None)
        self.open_btn.setEnabled(not busy)
        self.open_action.setEnabled(not busy)
        self.profile_combo.setEnabled(not busy)

    @Slot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def _on_success(self, out_dir: Path, paths: list[Path]) -> None:
        count = len(paths)
        noun = "file" if count == 1 else "files"
        self._set_status(f"Exported {count} {noun} to {out_dir}", folder=out_dir)

    @Slot(str)
    def _on_failure(self, message: str) -> None:
        self._set_status(message)
        if not message.startswith("Export cancelled"):
            QMessageBox.critical(self, "Export failed", message)

    @Slot()
    def _on_thread_finished(self) -> None:
        if self._thread is not None:
            self._thread.deleteLater()
        if self._worker is not None:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None
        self._set_busy(False)

    @Slot()
    def cancel_export(self) -> None:
        """Stop the running export after its current file."""
        if self._worker is not None:
            self._worker.cancel()
            self.cancel_btn.setEnabled(False)
            self._set_status("Cancelling…")

    @Slot()
    def show_output_folder(self) -> None:
        """Open the last export folder in the file manager."""
        if self._last_output is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output)))

    @Slot()
    def show_about(self) -> None:
        """Show version and links."""
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Export one image to any format, size, screen or platform.</p>"
            f'<p><a href="{REPO_URL}">{REPO_URL}</a><br>MIT License · Randy Northrup</p>',
        )


def create_app(argv: Sequence[str]) -> QApplication:
    """Create (or reuse) the QApplication with Pixport's identity set."""
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(APP_NAME)
    QApplication.setApplicationVersion(__version__)
    QApplication.setDesktopFileName(APP_ID)
    return QApplication(list(argv))


def self_test() -> int:
    """Export the bundled logo through every profile; 0 when every file is written.

    Used by the release pipeline to prove a packaged build can render SVG, write
    every format and build its window, on each operating system.
    """
    import tempfile  # noqa: PLC0415 - only needed for this diagnostic path

    logo = resources.files("pixport") / "assets" / "pixport.svg"
    failures = 0
    with resources.as_file(logo) as svg, tempfile.TemporaryDirectory() as tmp:
        settings = QSettings(str(Path(tmp) / "settings.ini"), QSettings.Format.IniFormat)
        window = MainWindow(settings)
        if not window.load_source(svg):
            return 1
        window.refresh_preview()
        for profile in PROFILES:
            job = Job(svg, Path(tmp), profile.formats[0], 256, 256, RenderOptions())
            try:
                written = profile.run(job)
            except (OSError, ValueError) as exc:
                print(f"FAIL {profile.id}: {exc}", file=sys.stderr)
                failures += 1
                continue
            missing = [p for p in written if not p.is_file()]
            failures += bool(missing)
            print(f"{'FAIL' if missing else 'ok  '} {profile.id}: {len(written)} file(s)")
        window.deleteLater()
    print("self-test passed" if not failures else f"self-test failed: {failures}")
    return 1 if failures else 0


def open_window(args: Sequence[str], settings: QSettings | None = None) -> MainWindow:
    """Show the main window and open the first file argument, if any."""
    window = MainWindow(settings)
    window.show()
    files = [Path(a) for a in args[1:] if not a.startswith("-")]
    if files:
        window.load_source(files[0])
    return window


def main(argv: Sequence[str] | None = None) -> int:
    """Open the window; an optional file argument is opened straight away."""
    args = list(sys.argv if argv is None else argv)
    if "--self-test" in args:
        create_app(args)
        return self_test()
    app = create_app(args)
    window = open_window(args)  # noqa: F841 - kept alive for the event loop
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
