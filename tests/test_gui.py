"""The real main window, driven offscreen."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from pixport.gui import widgets
from pixport.gui.app import MainWindow
from pixport.profiles import get_profile

pytestmark = pytest.mark.usefixtures("qt_app", "messages")


@pytest.fixture
def settings(tmp_path: Path) -> QSettings:
    """Settings in a temp ini file, so tests never touch the user's real ones."""
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def messages(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Capture message boxes instead of blocking on them."""
    seen: list[tuple[str, str]] = []
    for kind in ("warning", "critical", "information"):
        monkeypatch.setattr(
            QMessageBox,
            kind,
            staticmethod(lambda *a, kind=kind: seen.append((kind, str(a[2])))),
        )
    return seen


@pytest.fixture
def window(settings: QSettings) -> Iterator[MainWindow]:
    """A shown main window with isolated settings."""
    win = MainWindow(settings)
    win.resize(1000, 700)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def _wait_idle(win: MainWindow, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while win._thread is not None:
        QApplication.processEvents()
        if time.monotonic() > deadline:
            pytest.fail("export did not finish")
        time.sleep(0.01)
    QApplication.processEvents()


def _wait_preview(win: MainWindow, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while not win.preview_idle or win._preview_shown < win._preview_seq:
        QApplication.processEvents()
        if time.monotonic() > deadline:
            pytest.fail("preview did not finish")
        time.sleep(0.005)
    QApplication.processEvents()


def _select(win: MainWindow, profile_id: str) -> None:
    win.profile_combo.setCurrentIndex(win.profile_combo.findData(profile_id))


def test_starts_empty(window: MainWindow) -> None:
    assert window.source is None
    assert not window.export_btn.isEnabled()
    assert window.canvas._pixmap is None


def test_load_source_previews(window: MainWindow, square_svg: Path) -> None:
    assert window.load_source(square_svg)
    _wait_preview(window)
    assert window.canvas._pixmap is not None
    assert window.export_btn.isEnabled()
    assert "100 × 100" in window.source_meta.text()  # noqa: RUF001


def test_bad_source_warns(
    window: MainWindow, tmp_path: Path, messages: list[tuple[str, str]]
) -> None:
    bad = tmp_path / "x.txt"
    bad.write_text("x", encoding="utf-8")
    assert not window.load_source(bad)
    assert messages[-1][0] == "warning"
    assert window.source is None


def test_profile_switch_controls(window: MainWindow) -> None:
    _select(window, "convert")
    assert window.size_row.isVisibleTo(window)
    assert window.format_combo.count() == 6
    _select(window, "windows-ico")
    assert not window.size_row.isVisibleTo(window)
    assert window.format_combo.currentText() == "ICO"
    assert not window.format_combo.isEnabled()


def test_profiles_in_menu_match_registry(window: MainWindow) -> None:
    ids = [window.profile_combo.itemData(i) for i in range(window.profile_combo.count())]
    ids = [i for i in ids if i]  # separators carry no data
    for profile_id in ids:
        get_profile(profile_id)
    assert len(ids) == 11


def test_aspect_lock(window: MainWindow, wide_svg: Path) -> None:
    window.lock_btn.setChecked(True)
    window.load_source(wide_svg)
    window.width_spin.setValue(400)
    assert window.height_spin.value() == 200
    window.height_spin.setValue(50)
    assert window.width_spin.value() == 100
    window.lock_btn.setChecked(False)
    window.height_spin.setValue(300)
    assert window.width_spin.value() == 100


def test_preview_honours_forced_opacity(window: MainWindow, square_svg: Path) -> None:
    window.load_source(square_svg)
    window.transparent_chk.setChecked(True)
    _select(window, "ios")
    assert not window.render_options().transparent
    assert "cannot be transparent" in window.bg_hint.text()
    _select(window, "convert")
    window.format_combo.setCurrentText("JPG")
    assert not window.render_options().transparent
    window.format_combo.setCurrentText("PNG")
    assert window.render_options().transparent


def test_export_runs_on_worker_thread(window: MainWindow, square_svg: Path, out_dir: Path) -> None:
    window.load_source(square_svg)
    _select(window, "android")
    window.start_export(out_dir)
    assert window.cancel_btn.isVisibleTo(window)
    _wait_idle(window)
    assert (out_dir / "square-android" / "playstore-icon.png").is_file()
    assert "Exported 24 files" in window.status_text.text()
    assert window.show_folder_btn.isVisibleTo(window)
    assert window.export_btn.isVisibleTo(window)


def test_export_failure_is_reported(
    window: MainWindow, square_svg: Path, tmp_path: Path, messages: list[tuple[str, str]]
) -> None:
    window.load_source(square_svg)
    blocker = tmp_path / "file-not-folder"
    blocker.write_text("x", encoding="utf-8")
    _select(window, "linux")
    window.start_export(blocker)
    _wait_idle(window)
    assert messages[-1][0] == "critical"
    assert not window.show_folder_btn.isVisibleTo(window)


def test_worker_cancel(square_svg: Path, out_dir: Path) -> None:
    from pixport.profiles import Job

    worker = widgets.ExportWorker(get_profile("wallpaper-phone"), Job(square_svg, out_dir))
    failures: list[str] = []
    worker.failed.connect(failures.append)
    worker.progressed.connect(lambda done, _total: worker.cancel() if done == 1 else None)
    worker.run()
    assert failures
    assert failures[0].startswith("Export cancelled")
    assert len(list(out_dir.rglob("*.png"))) == 2


def test_settings_round_trip(settings: QSettings) -> None:
    first = MainWindow(settings)
    _select(first, "wallpaper-phone")
    first.format_combo.setCurrentText("WEBP")
    first.padding_spin.setValue(12)
    first.zoom_slider.setValue(55)
    first.transparent_chk.setChecked(False)
    first.background = (1, 2, 3)
    first.save_settings()
    first.deleteLater()

    second = MainWindow(settings)
    assert second.current_profile().id == "wallpaper-phone"
    assert second.current_format() == "webp"
    assert second.padding_spin.value() == 12
    assert second.zoom_slider.value() == 55
    assert not second.transparent_chk.isChecked()
    assert second.background == (1, 2, 3)
    second.deleteLater()


def test_corrupt_settings_fall_back(settings: QSettings) -> None:
    settings.setValue("padding", "lots")
    settings.setValue("profile", "deleted-profile")
    win = MainWindow(settings)
    assert win.padding_spin.value() == 0
    assert win.current_profile().id == "convert"
    win.deleteLater()


def test_dropped_file_filter(tmp_path: Path) -> None:
    assert (
        widgets.dropped_file([str(tmp_path / "a.txt"), str(tmp_path / "b.SVG")])
        == tmp_path / "b.SVG"
    )
    assert widgets.dropped_file([str(tmp_path / "a.txt")]) is None


def test_theme_switch_repaints(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    from pixport.gui import app as gui_app
    from pixport.gui import theme

    monkeypatch.setattr(gui_app, "system_theme", lambda: theme.DARK)
    window.apply_system_theme()
    assert window.canvas._theme is theme.DARK
    assert theme.DARK.window in (QApplication.instance().styleSheet())  # type: ignore[union-attr]


def test_self_test_passes(capsys: pytest.CaptureFixture[str]) -> None:
    from pixport.gui.app import main

    assert main(["pixport", "--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out


def test_default_window_fits_small_screens() -> None:
    from PySide6.QtCore import QSize

    from pixport.gui.app import default_window_size

    assert default_window_size(QSize(2560, 1400)) == QSize(1180, 760)
    assert default_window_size(QSize(1024, 728)) == QSize(921, 655)


def test_saved_window_size_is_restored(settings: QSettings, square_svg: Path) -> None:
    """In 2.0.0 the launcher resized the window after restoring it, losing the saved size."""
    from pixport.gui.app import open_window

    first = open_window(["pixport"], settings)
    first.resize(760, 540)
    first.save_settings()
    first.close()
    second = open_window(["pixport", str(square_svg)], settings)
    assert (second.width(), second.height()) == (760, 540)
    assert second.source == square_svg
    second.close()


def test_preview_renders_off_the_ui_thread(window: MainWindow, square_svg: Path) -> None:
    """Bursts of changes keep one render running and only the newest waiting."""
    window.load_source(square_svg)
    for value in range(10, 60, 5):
        window.padding_spin.setValue(value)
        window.refresh_preview()
        assert window._preview_pending is None or window._preview_busy
    _wait_preview(window)
    assert window._preview_shown == window._preview_seq
    assert window.canvas._pixmap is not None


def test_preview_error_shows_message(window: MainWindow, tmp_path: Path) -> None:
    svg = tmp_path / "later-broken.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>', "utf-8")
    window.load_source(svg)
    _wait_preview(window)
    svg.write_text("<svg", encoding="utf-8")
    import os

    st = svg.stat()
    os.utime(svg, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    window.refresh_preview()
    _wait_preview(window)
    assert window.canvas._pixmap is None
    assert "Cannot preview" in window.canvas._message


def test_closing_during_preview_is_safe(settings: QSettings, square_svg: Path) -> None:
    win = MainWindow(settings)
    win.load_source(square_svg)
    win.close()
    win.deleteLater()
    QApplication.processEvents()
    from PySide6.QtCore import QThreadPool

    assert QThreadPool.globalInstance().waitForDone(20_000)
    QApplication.processEvents()


def test_preview_render_thread_is_not_ui_thread(
    window: MainWindow, square_svg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    real = widgets.render_preview
    threads: list[int] = []

    def spy(*args: object, **kwargs: object) -> object:
        threads.append(threading.get_ident())
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(widgets, "render_preview", spy)
    window.load_source(square_svg)
    _wait_preview(window)
    assert threads
    assert threading.get_ident() not in threads
