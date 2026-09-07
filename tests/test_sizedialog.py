"""글자 크기를 한 번에 바꾸는 대화상자.

같은 값으로 맞추기와 배율은 서로 다른 일이다. 전부 12pt로 만들면 제목과
눈금이 같아져 그림의 위계가 사라진다. 어느 쪽인지 대화상자가 분명히
돌려주지 않으면, 버튼 한 번에 그림이 납작해진다.
"""

import os

import pytest

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module", autouse=True)
def _offscreen():
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        return app
    try:
        return QApplication([])
    except Exception as exc:                    # pragma: no cover
        pytest.skip(f"Qt를 띄울 수 없습니다: {exc}")


def _dialog(current=10.0):
    from figtune.ui.qt.fontpicker import SizeDialog
    return SizeDialog(current=current)


def test_it_opens_on_the_size_that_is_already_there(qapp):
    """고정값을 채우면 확인만 눌러도 그림이 바뀐다."""
    dlg = _dialog(current=13.5)
    assert dlg.choice() == ("absolute", 13.5)


def test_choosing_the_scale_changes_what_it_reports(qapp):
    dlg = _dialog()
    dlg.by.setChecked(True)
    dlg.factor.setValue(1.5)
    assert dlg.choice() == ("scale", 1.5)


def test_only_the_chosen_number_can_be_touched(qapp):
    """둘 다 만질 수 있으면 쓰지 않을 값을 고치고 아무 일도 안 일어난다."""
    dlg = _dialog()
    assert (dlg.size.isEnabled(), dlg.factor.isEnabled()) == (True, False)
    dlg.by.setChecked(True)
    assert (dlg.size.isEnabled(), dlg.factor.isEnabled()) == (False, True)


def test_the_scale_never_reaches_zero(qapp):
    """0배는 글자를 지운다 — 되돌리기 전에는 무슨 일이 났는지도 안 보인다."""
    dlg = _dialog()
    dlg.factor.setValue(0.0)
    assert dlg.factor.value() > 0
