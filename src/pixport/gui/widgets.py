"""Custom widgets: the preview canvas and the background export worker."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint, QRectF, Qt, Signal, Slot
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from pixport.gui.theme import LIGHT, Theme
from pixport.render import SUPPORTED_SUFFIXES

if TYPE_CHECKING:
    from PIL import Image

    from pixport.profiles import Job, Profile

CHECKER_TILE = 10
CANVAS_MARGIN = 28
CORNER_RADIUS = 14


def pil_to_qimage(img: Image.Image) -> QImage:
    """Convert a Pillow image to a QImage that owns its pixels."""
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888)
    return qimg.copy()


def dropped_file(urls: list[str]) -> Path | None:
    """Return the first local file with a supported extension, if any."""
    for url in urls:
        path = Path(url)
        if path.suffix.lower() in SUPPORTED_SUFFIXES:
            return path
    return None


class PreviewCanvas(QWidget):
    """Shows the rendered output on a checkerboard; doubles as the drop target."""

    file_dropped = Signal(Path)
    open_requested = Signal()
    resized = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create an empty canvas that invites a drop."""
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumSize(360, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Preview")
        self.setAccessibleDescription(
            "Shows the export result. Drop an image here, or click to open one."
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme = LIGHT
        self._pixmap: QPixmap | None = None
        self._message = "Drop an SVG or image here\nor click to open"
        self._hover = False

    def set_theme(self, theme: Theme) -> None:
        """Repaint with ``theme`` colours."""
        self._theme = theme
        self.update()

    def set_image(self, img: QImage) -> None:
        """Show ``img``. Its device pixel ratio must already be set."""
        self._pixmap = QPixmap.fromImage(img)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def set_message(self, text: str) -> None:
        """Clear the image and show ``text`` instead."""
        self._pixmap = None
        self._message = text
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def available_pixels(self) -> tuple[int, int]:
        """Device-pixel area available for the rendered image."""
        dpr = self.devicePixelRatioF()
        w = max(1, self.width() - 2 * CANVAS_MARGIN)
        h = max(1, self.height() - 2 * CANVAS_MARGIN)
        return (round(w * dpr), round(h * dpr))

    # ── painting ──

    def _checker_brush(self) -> QBrush:
        tile = QPixmap(CHECKER_TILE * 2, CHECKER_TILE * 2)
        tile.fill(QColor(self._theme.checker_b))
        p = QPainter(tile)
        p.fillRect(0, 0, CHECKER_TILE, CHECKER_TILE, QColor(self._theme.checker_a))
        p.fillRect(
            CHECKER_TILE, CHECKER_TILE, CHECKER_TILE, CHECKER_TILE, QColor(self._theme.checker_a)
        )
        p.end()
        return QBrush(tile)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the checkerboard, the image, or the drop prompt."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        t = self._theme
        p.fillRect(self.rect(), QColor(t.window))

        if self._pixmap is None:
            area = QRectF(self.rect()).adjusted(
                CANVAS_MARGIN, CANVAS_MARGIN, -CANVAS_MARGIN, -CANVAS_MARGIN
            )
            pen = QPen(QColor(t.accent if self._hover else t.border), 2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(QColor(t.surface))
            p.drawRoundedRect(area, CORNER_RADIUS, CORNER_RADIUS)
            p.setPen(QColor(t.muted))
            font = p.font()
            font.setPointSizeF(font.pointSizeF() * 1.15)
            p.setFont(font)
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, self._message)
            p.end()
            return

        dpr = self._pixmap.devicePixelRatio()
        logical_w = self._pixmap.width() / dpr
        logical_h = self._pixmap.height() / dpr
        x = (self.width() - logical_w) / 2
        y = (self.height() - logical_h) / 2
        target = QRectF(x, y, logical_w, logical_h)
        p.setBrushOrigin(QPoint(round(x), round(y)))
        p.fillRect(target, self._checker_brush())
        p.drawPixmap(target.topLeft(), self._pixmap)
        p.setPen(QPen(QColor(t.accent if self._hover else t.border), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(target.adjusted(-0.5, -0.5, 0.5, 0.5))
        p.end()

    # ── interaction ──

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Ask the window to re-render at the new size."""
        super().resizeEvent(event)
        self.resized.emit()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Click on the empty canvas opens a file."""
        if self._pixmap is None and event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double-click always opens a file."""
        self.open_requested.emit()
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept drags carrying a supported file."""
        urls = [u.toLocalFile() for u in event.mimeData().urls()]
        if dropped_file(urls):
            event.acceptProposedAction()
            self._hover = True
            self.update()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        """Clear the hover highlight."""
        self._hover = False
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Emit the dropped file."""
        self._hover = False
        self.update()
        path = dropped_file([u.toLocalFile() for u in event.mimeData().urls()])
        if path:
            event.acceptProposedAction()
            self.file_dropped.emit(path)


class Cancelled(Exception):  # noqa: N818 - reads as a state, like StopIteration
    """Raised inside the progress callback to stop an export."""


class ExportWorker(QObject):
    """Runs one profile export off the UI thread."""

    progressed = Signal(int, int)
    succeeded = Signal(object)  # list[Path]
    failed = Signal(str)
    done = Signal()

    def __init__(self, profile: Profile, job: Job) -> None:
        """Prepare an export; call :meth:`run` (normally from a QThread)."""
        super().__init__()
        self._profile = profile
        self._job = job
        self._cancel = False

    def cancel(self) -> None:
        """Stop after the file currently being written."""
        self._cancel = True

    def _progress(self, done: int, total: int) -> None:
        if self._cancel:
            raise Cancelled
        self.progressed.emit(done, total)

    @Slot()
    def run(self) -> None:
        """Export and report the outcome through signals."""
        try:
            written = self._profile.run(self._job, self._progress)
        except Cancelled:
            self.failed.emit("Export cancelled. Files already written were kept.")
        # Broad catch is deliberate: an exception escaping a worker slot would
        # vanish silently in another thread. Every failure becomes a message.
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc) or type(exc).__name__)
        else:
            self.succeeded.emit(written)
        finally:
            self.done.emit()
