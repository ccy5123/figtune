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


# --- 조립 화면 ---------------------------------------------------------------

@pytest.fixture
def funcform(tmp_path):
    """plot(ax)를 노출하는 패널들 — 모드 B로 합칠 수 있는 형태."""
    src = ("import matplotlib.pyplot as plt\n\n"
           "def plot(ax):\n"
           "    ax.plot([0, 1, 2], [0, 1, 4], 'o-')\n"
           "    ax.set_title({t!r})\n")
    out = []
    for name in ("wide", "a", "b"):
        p = tmp_path / f"{name}.py"
        p.write_text(src.format(t=name), encoding="utf-8")
        out.append(p)
    return out


@pytest.fixture
def composer(qapp, funcform):
    from figtune.ui.qt.main import MainWindow
    from figtune.ui.qt.montagedialog import MontageDialog

    w = MainWindow(funcform[0])
    for p in funcform[1:]:
        w.open_document(p)
    dlg = MontageDialog(w, 2, 2)
    yield w, dlg, funcform
    dlg.deleteLater()
    w.close()


def test_saving_is_locked_until_every_cell_is_filled(composer):
    """빈 칸이 남은 채로 만들면 그 자리가 빈 그림이 나온다."""
    from PySide6.QtWidgets import QDialogButtonBox

    _w, dlg, scripts = composer
    save = dlg.buttons.button(QDialogButtonBox.Save)
    assert not save.isEnabled()

    for i, _s in enumerate(dlg.model.slots):
        dlg.model.assign(i, str(scripts[i % len(scripts)]) + f"#{i}")
    dlg._sync_buttons()
    assert save.isEnabled()


def test_merging_shows_one_wide_cell(composer):
    _w, dlg, _s = composer
    dlg.grid._region = (0, 0, 0, 1)          # 첫 행 두 칸을 고른 상태
    dlg._merge()
    assert (0, 0, 1, 2) in [(s.row, s.col, s.rowspan, s.colspan)
                            for s in dlg.model.slots]
    assert len(dlg.model.slots) == 3


def test_merge_button_needs_more_than_one_cell(composer):
    _w, dlg, _s = composer
    dlg.grid._region = (0, 0, 0, 0)
    dlg._sync_buttons()
    assert not dlg.btn_merge.isEnabled()

    dlg.grid._region = (0, 0, 0, 1)
    dlg._sync_buttons()
    assert dlg.btn_merge.isEnabled()


def test_splitting_a_merged_cell_restores_it(composer):
    _w, dlg, _s = composer
    dlg.grid._region = (0, 0, 0, 1)
    dlg._merge()
    dlg.grid._region = (0, 0, 0, 0)
    dlg._split()
    assert len(dlg.model.slots) == 4


def test_the_composer_offers_the_open_tabs(composer):
    """+를 눌렀을 때 고를 것은 지금 열려 있는 탭들이다."""
    w, _dlg, scripts = composer
    assert [d.name for d in w.documents()] == [p.name for p in scripts]


def test_unmergeable_tabs_are_shown_with_the_reason(composer, tmp_path):
    """합칠 수 없다는 것을 칸을 다 채우고 나서 알면 늦다.

    목록에서 빼 버리면 '내 파일이 왜 없지'가 되므로, 고를 수 없게 두되
    이유를 함께 보여준다.
    """
    w, dlg, _s = composer
    plain = tmp_path / "plain.py"
    plain.write_text("import matplotlib.pyplot as plt\n"
                     "fig, ax = plt.subplots()\n"
                     "ax.plot([0, 1], [0, 1])\n", encoding="utf-8")
    w.open_document(plain)

    by_name = {n: why for n, _p, why in dlg.candidates()}
    assert by_name["wide.py"] is None
    assert "plot(ax)" in by_name["plain.py"]


def test_placing_an_unmergeable_script_is_refused(composer, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    _w, dlg, _s = composer
    plain = tmp_path / "plain.py"
    plain.write_text("import matplotlib.pyplot as plt\n"
                     "fig, ax = plt.subplots()\n", encoding="utf-8")
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))

    assert dlg.place(0, str(plain)) is False
    assert dlg.model.slots[0].ref is None


def test_placing_a_good_script_works(composer):
    _w, dlg, scripts = composer
    assert dlg.place(0, str(scripts[0])) is True
    assert dlg.model.slots[0].ref == str(scripts[0])
