"""Command line behaviour and exit codes."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from pixport import __version__
from pixport.cli import main
from pixport.profiles import PROFILES


def test_list_profiles(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--list-profiles"]) == 0
    out = capsys.readouterr().out
    for profile in PROFILES:
        assert profile.id in out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_default_profile_is_convert(square_svg: Path, out_dir: Path) -> None:
    assert main([str(square_svg), "-o", str(out_dir), "-q"]) == 0
    assert (out_dir / "square_1024x1024.png").is_file()


def test_several_profiles_and_inputs(square_svg: Path, square_png: Path, out_dir: Path) -> None:
    code = main(
        [
            str(square_svg),
            str(square_png),
            "-p",
            "windows-ico",
            "-p",
            "macos-icns",
            "-o",
            str(out_dir),
        ]
    )
    assert code == 0
    names = {p.name for p in out_dir.iterdir()}
    assert names == {"square.ico", "square_1.ico", "square.icns", "square_1.icns"}


def test_format_applies_only_where_supported(square_svg: Path, out_dir: Path) -> None:
    assert (
        main(
            [
                str(square_svg),
                "-p",
                "android",
                "-p",
                "windows-ico",
                "-f",
                "webp",
                "-o",
                str(out_dir),
                "-q",
            ]
        )
        == 0
    )
    assert (out_dir / "square-android" / "mipmap-mdpi" / "ic_launcher.webp").is_file()
    assert (out_dir / "square.ico").is_file()


def test_size_padding_zoom_background(square_svg: Path, out_dir: Path) -> None:
    args = [str(square_svg), "-o", str(out_dir), "-q", "--width", "100", "--height", "50"]
    args += ["--padding", "5", "--zoom", "50", "--background", "#0000ff"]
    assert main(args) == 0
    with Image.open(out_dir / "square_100x50.png") as img:
        assert img.mode == "RGB"
        assert img.getpixel((0, 0)) == (0, 0, 255)
        assert img.getpixel((50, 25)) == (255, 0, 0)
        assert img.getpixel((30, 25)) == (0, 0, 255)  # zoom 50 % leaves the sides empty


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["-p", "nope"], "Unknown profile"),
        (["-p", "windows-ico", "-f", "png"], "no chosen profile writes"),
    ],
)
def test_usage_errors_exit_2(
    square_svg: Path,
    out_dir: Path,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    message: str,
) -> None:
    assert main([str(square_svg), "-o", str(out_dir), *args]) == 2
    assert message in capsys.readouterr().err


def test_missing_input_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / "missing.svg")]) == 2
    assert "not found" in capsys.readouterr().err


@pytest.mark.parametrize(
    "bad",
    [["--width", "0"], ["--zoom", "5"], ["--padding", "-1"], ["--background", "nah"]],
)
def test_argument_validation(square_svg: Path, bad: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([str(square_svg), *bad])
    assert exc.value.code == 2


def test_render_failure_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    broken = tmp_path / "broken.svg"
    broken.write_text("<svg", encoding="utf-8")
    assert main([str(broken), "-o", str(tmp_path)]) == 1
    assert "broken.svg -> convert" in capsys.readouterr().err


def test_no_inputs_opens_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    import pixport.gui.app

    monkeypatch.setattr(pixport.gui.app, "main", lambda: 7)
    assert main([]) == 7
