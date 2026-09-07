"""여러 문서를 탭으로 연다.

병합하려면 합칠 그림들을 동시에 열고 있어야 한다. 그런데 창 하나가 세션
하나만 쥐고 있으면 그럴 수 없다.

문서마다 따로 가져야 하는 것과 창이 하나만 가져야 하는 것을 가르는 것이
핵심이다. 세션·캔버스·보기 도구·선택·실행 취소는 문서의 것이고, 트리와
인스펙터는 지금 보고 있는 문서를 비추는 창의 것이다. 섞이면 A 탭에서 고른
것이 B 탭에 적용되는 종류의 사고가 난다.
"""

import os
import shutil
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

import matplotlib
matplotlib.use("Agg")

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "plot_fig3.py"


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
    except Exception as exc:                     # pragma: no cover - 환경 의존
        pytest.skip(f"Qt를 띄울 수 없습니다: {exc}")


@pytest.fixture
def scripts(tmp_path):
    out = []
    for name in ("one", "two", "three"):
        p = tmp_path / f"{name}.py"
        shutil.copy(EXAMPLE, p)
        out.append(p)
    return out


@pytest.fixture
def win(qapp, scripts):
    from figtune.ui.qt.main import MainWindow

    w = MainWindow(scripts[0])
    w.canvas.draw()
    yield w
    w.close()


# --- 여러 문서 --------------------------------------------------------------

def test_one_script_opens_one_tab(win):
    assert win.document_count() == 1


def test_opening_another_script_adds_a_tab(win, scripts):
    win.open_document(scripts[1])
    assert win.document_count() == 2
    assert win.documents()[0].session is not win.documents()[1].session


def test_the_new_tab_becomes_active(win, scripts):
    win.open_document(scripts[1])
    assert win.session.script.name == "two.py"


def test_switching_tabs_switches_the_session(win, scripts):
    win.open_document(scripts[1])
    win.activate_document(0)
    assert win.session.script.name == "one.py"
    win.activate_document(1)
    assert win.session.script.name == "two.py"


def test_each_tab_keeps_its_own_selection(win, scripts):
    """A 탭에서 고른 것이 B 탭에 딸려 가면 엉뚱한 것이 고쳐진다."""
    win.select("ax0.title")
    win.open_document(scripts[1])
    assert win.selection() == []

    win.select("ax1.title")
    win.activate_document(0)
    assert win.selection() == ["ax0.title"]


def test_edits_land_on_the_active_document_only(win, scripts):
    win.open_document(scripts[1])
    win.select("ax0.line0")
    win.inspector.edited.emit("color", "#c0392b")

    assert win.documents()[1].session.spec.get("ax0.line0", "color") == "#c0392b"
    assert win.documents()[0].session.spec.get("ax0.line0", "color") is None


def test_undo_is_per_document(win, scripts):
    """실행 취소가 창 하나로 묶여 있으면 다른 탭의 편집이 되돌아간다."""
    win.session.set_prop("ax0.line0", "color", "#111111")
    win.open_document(scripts[1])
    win.session.set_prop("ax0.line0", "color", "#222222")

    win.undo()
    assert win.documents()[1].session.spec.get("ax0.line0", "color") is None
    assert win.documents()[0].session.spec.get("ax0.line0", "color") == "#111111"


def test_the_tree_follows_the_active_document(win, scripts):
    from PySide6.QtCore import Qt

    win.open_document(scripts[1])
    win.session.set_prop("ax0.title", "text", "두 번째")
    win.reload_tree()
    labels = [it.text(0) for it in
              win.tree.findItems("", Qt.MatchContains | Qt.MatchRecursive, 0)]
    assert any("두 번째" in t for t in labels)

    win.activate_document(0)
    labels = [it.text(0) for it in
              win.tree.findItems("", Qt.MatchContains | Qt.MatchRecursive, 0)]
    assert not any("두 번째" in t for t in labels)


def test_closing_a_tab_leaves_the_others(win, scripts):
    win.open_document(scripts[1])
    win.open_document(scripts[2])
    win.close_document(1)
    assert win.document_count() == 2
    assert [d.session.script.name for d in win.documents()] == \
        ["one.py", "three.py"]


def test_the_last_tab_is_not_closed(win):
    """빈 창은 아무것도 할 수 없는 상태다 — 들어갈 이유가 없다."""
    win.close_document(0)
    assert win.document_count() == 1


def test_the_same_script_is_not_opened_twice(win, scripts):
    """같은 파일이 두 탭에 있으면 어느 쪽 편집이 저장되는지 알 수 없다."""
    win.open_document(scripts[0])
    assert win.document_count() == 1


def test_view_toolbar_belongs_to_its_document(win, scripts):
    """확대·이동 상태가 창에 하나면 탭을 옮겨도 켜진 채로 남는다."""
    win.open_document(scripts[1])
    assert win.toolbar is win.documents()[1].toolbar
    win.activate_document(0)
    assert win.toolbar is win.documents()[0].toolbar


def test_dirty_marks_only_its_own_tab(win, scripts):
    win.open_document(scripts[1])
    win.session.set_prop("ax0.line0", "color", "#c0392b")
    win.mark_dirty()
    assert win.tab_label(1).endswith("*")
    assert not win.tab_label(0).endswith("*")


def test_a_new_tab_gets_its_own_view_baseline(win, scripts):
    """기준선이 없으면 그 탭에서는 '범위 적용'이 영영 켜지지 않는다.

    확대해 놓고 남기려는데 버튼이 죽어 있으면 사용자는 기능이 없는 줄 안다.
    """
    win.open_document(scripts[1])
    assert win._view_baseline, "새 탭의 보기 기준선이 비어 있습니다"

    ax = win.session.fig.axes[0]
    ax.set_xlim(ax.get_xlim()[0], ax.get_xlim()[1] / 2)
    assert win._view_changes(), "보기 변화가 잡히지 않습니다"
