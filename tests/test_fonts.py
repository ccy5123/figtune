"""한글 렌더 가능 여부 판정.

이 판정이 틀리면 두 가지로 잘못된다. 거짓 음성이면 한글이 멀쩡한 환경에서
멋대로 영어가 되고, 거짓 양성이면 화면이 통째로 네모가 된 채 방치된다.
후자가 더 나쁘다 — 사용자가 원인을 알 길이 없기 때문이다.

fonts 모듈은 Qt를 모듈 수준에서 import하지 않는다. 그래서 PySide6가 없는
CI에서도 명령 안내 부분은 그대로 검사할 수 있다.
"""

import os
import sys

import pytest

from figtune.ui.qt import fonts


def _os_release(tmp_path, text):
    p = tmp_path / "os-release"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.skipif(sys.platform != "linux", reason="리눅스 전용 경로")
@pytest.mark.parametrize("content,expected", [
    ('ID=ubuntu\nID_LIKE=debian\n', "apt"),
    ('ID=debian\n', "apt"),
    ('ID=fedora\n', "dnf"),
    ('ID=arch\n', "pacman"),
    ('ID="opensuse-leap"\nID_LIKE="suse"\n', "zypper"),
    ('ID=alpine\n', "apk"),
])
def test_install_command_matches_the_distro(tmp_path, content, expected):
    cmd = fonts.install_command(_os_release(tmp_path, content))
    assert expected in cmd


@pytest.mark.skipif(sys.platform != "linux", reason="리눅스 전용 경로")
def test_unknown_distro_falls_back_to_apt(tmp_path):
    """WSL 기본이 우분투라 apt 안내가 가장 자주 맞는다."""
    cmd = fonts.install_command(_os_release(tmp_path, "ID=plan9\n"))
    assert "apt" in cmd


@pytest.mark.skipif(sys.platform != "linux", reason="리눅스 전용 경로")
def test_missing_os_release_still_gives_a_command(tmp_path):
    cmd = fonts.install_command(tmp_path / "nope")
    assert cmd and "fc-cache" in cmd


def test_install_command_mentions_cache_refresh(tmp_path):
    """폰트만 깔고 fc-cache를 빼면 Qt가 새 폰트를 못 본다."""
    if sys.platform != "linux":
        pytest.skip("리눅스 전용 경로")
    for content in ("ID=ubuntu\n", "ID=fedora\n", "ID=arch\n"):
        assert "fc-cache" in fonts.install_command(_os_release(tmp_path, content))


def test_sample_is_a_precomposed_syllable():
    """자모 하나로 재면 조합 폰트가 있는 환경에서 오판할 수 있다."""
    assert fonts.SAMPLE == "가"
    assert "가" <= fonts.SAMPLE <= "힣"


def test_can_render_reports_a_bool(monkeypatch):
    """QApplication이 있어야만 의미가 있다. 없으면 Qt가 죽으므로 만들고 잰다."""
    pytest.importorskip("PySide6.QtWidgets")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    assert isinstance(fonts.can_render(), bool)
