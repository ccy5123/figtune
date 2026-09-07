"""캔버스 직접 조작.

세 가지 조작이 한 제스처를 놓고 겹친다.
  · 텍스트를 한 번 클릭 → 그 자리에 캐럿
  · 같은 텍스트를 끌기   → 위치 이동
  · 축 상자 모서리 끌기  → 크기 변경

누른 시점에는 클릭인지 끌기인지 알 수 없다. 그래서 움직인 거리로 가른다.
이 경계가 무너지면 글자를 고치려다 그림이 밀리거나, 옮기려다 편집기가 뜬다.
"""

import os
import shutil
from pathlib import Path

import pytest

# PySide6 자체는 import되지만 QtWidgets는 libEGL 같은 시스템
# 라이브러리를 요구한다. 없는 환경에서는 여기서 건너뛰어야 한다.
pytest.importorskip("PySide6.QtWidgets")

import matplotlib
matplotlib.use("Agg")

from matplotlib.backend_bases import MouseEvent

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "plot_fig3.py"


@pytest.fixture(scope="module", autouse=True)
def _offscreen():
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    """Qt 플랫폼 플러그인이 없는 환경(시스템 라이브러리 미설치)에서는 건너뛴다.

    import는 되는데 QApplication 생성에서 죽는 경우가 있어서, importorskip
    만으로는 막히지 않는다. 여기서 잡지 않으면 테스트가 실패가 아니라
    프로세스 중단으로 끝나 원인이 안 보인다.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        return app
    try:
        return QApplication([])
    except Exception as exc:                     # pragma: no cover - 환경 의존
        pytest.skip(f"Qt를 띄울 수 없습니다: {exc}")


@pytest.fixture
def win(qapp, tmp_path):
    from figtune.ui.qt.main import MainWindow

    script = tmp_path / "plot_fig3.py"
    shutil.copy(EXAMPLE, script)
    w = MainWindow(script)
    w.canvas.draw()
    yield w
    w.close()


def press(c, x, y, dbl=False):
    c._press(MouseEvent("button_press_event", c, x, y, 1, dblclick=dbl))


def move(c, x, y):
    c._motion(MouseEvent("motion_notify_event", c, x, y, None))


def release(c, x, y):
    c._release(MouseEvent("button_release_event", c, x, y, 1))


def click(c, x, y, jitter=1.0):
    """누르고 거의 안 움직이고 뗀다 — 손떨림 수준."""
    press(c, x, y)
    move(c, x + jitter, y)
    release(c, x + jitter, y)


def drag(c, x0, y0, x1, y1):
    press(c, x0, y0)
    move(c, x1, y1)
    release(c, x1, y1)


def sel_usertext(ax_i, tid):
    from figtune.core import selector as sel
    return sel.usertext(ax_i, tid)


def _tree_paths(win):
    from PySide6.QtCore import Qt
    return {it.data(0, Qt.UserRole) for it in
            win.tree.findItems("", Qt.MatchContains | Qt.MatchRecursive, 0)}


def center(win, artist):
    bb = artist.get_window_extent(win.canvas.get_renderer())
    return (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2


# --- 클릭과 끌기의 경계 ------------------------------------------------------

def test_click_on_a_title_opens_the_caret(win):
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.title))
    assert win.canvas.editor.active
    assert win.canvas.editor.text() == "Uptake"


def test_click_does_not_move_the_title(win):
    """캐럿을 놓으려던 클릭이 글자를 밀면 안 된다."""
    ax = win.session.fig.axes[0]
    before = list(ax.title.get_position())
    click(win.canvas, *center(win, ax.title))
    assert list(ax.title.get_position()) == before
    assert win.session.spec.of("ax0.title").get("position") is None


def test_dragging_a_title_moves_it_and_skips_the_editor(win):
    ax = win.session.fig.axes[0]
    x, y = center(win, ax.title)
    drag(win.canvas, x, y, x + 40, y + 8)
    assert not win.canvas.editor.active, "옮기려는데 편집기가 떴습니다"
    assert win.session.spec.of("ax0.title").get("position") is not None


def test_caret_lands_near_the_click(win):
    """글자 한가운데를 누르면 캐럿도 한가운데여야 한다."""
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.title))
    pos = win.canvas.editor.cursorPosition()
    assert 0 < pos < len("Uptake")


# --- 제자리 편집 -----------------------------------------------------------

def test_committing_updates_both_figure_and_spec(win):
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.title))
    win.canvas.editor.setText("Uptake (rev)")
    win.canvas.editor.commit()
    assert ax.title.get_text() == "Uptake (rev)"
    assert win.session.spec.of("ax0.title").get("text") == "Uptake (rev)"


def test_escape_leaves_everything_alone(win):
    """잘못 눌렀을 때 아무 일도 없어야 한다."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.title))
    win.canvas.editor.setText("망친 제목")
    win.canvas.editor.keyPressEvent(
        QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    assert not win.canvas.editor.active
    assert ax.title.get_text() == "Uptake"
    assert win.session.spec.of("ax0.title").get("text") is None


def test_unchanged_text_records_nothing(win):
    """열었다 그대로 닫으면 override가 생기면 안 된다."""
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.title))
    win.canvas.editor.commit()
    assert win.session.spec.of("ax0.title").get("text") is None


def test_clicking_elsewhere_commits(win):
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.title))
    win.canvas.editor.setText("확정됨")
    bb = ax.get_window_extent()
    press(win.canvas, bb.x0 + 30, bb.y0 + 20)
    assert not win.canvas.editor.active
    assert ax.title.get_text() == "확정됨"


def test_axis_label_is_editable_in_place(win):
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.xaxis.label))
    assert win.canvas.editor.active
    assert win.canvas.editor.text() == "Time (h)"


# --- 끌기 ------------------------------------------------------------------

def test_dragging_the_legend_pins_and_moves_it(win):
    ax = win.session.fig.axes[0]
    x, y = center(win, ax.get_legend())
    drag(win.canvas, x, y, x - 50, y - 30)
    over = win.session.spec.of("ax0.legend")
    assert over.get("bbox_to_anchor") is not None
    assert over.get("loc") in ("upper left", "upper right", "lower left",
                              "lower right", "center", "center left",
                              "center right", "upper center", "lower center")


def test_resizing_needs_a_selection_first(win):
    """핸들이 늘 살아 있으면 축선을 누르려는 클릭을 가로챈다."""
    ax = win.session.fig.axes[0]
    bb = ax.get_window_extent()
    drag(win.canvas, bb.x1, bb.y1, bb.x1 + 25, bb.y1 + 15)
    assert win.session.spec.of("ax0").get("position") is None


def test_resizing_after_selecting_changes_the_box(win):
    ax = win.session.fig.axes[0]
    win.select("ax0")
    bb = ax.get_window_extent()
    drag(win.canvas, bb.x1, bb.y1, bb.x1 + 25, bb.y1 + 15)
    got = win.session.spec.of("ax0").get("position")
    assert got is not None and len(got) == 4


def test_a_drag_is_one_undo_step(win):
    """마우스 이동마다 한 칸씩 쌓이면 실행 취소가 1픽셀을 되돌린다."""
    ax = win.session.fig.axes[0]
    x, y = center(win, ax.title)
    before = len(win.session.history._undo)
    press(win.canvas, x, y)
    for step in range(5, 45, 5):
        move(win.canvas, x + step, y)
    release(win.canvas, x + 40, y)
    assert len(win.session.history._undo) - before == 1


def test_undo_restores_the_figure_not_just_the_spec(win):
    """spec에서만 지우면 화면은 그대로다 — 되돌린 것처럼 보이지 않는다.

    figtune은 스크립트를 다시 돌리기 전까지 '원래 값'을 알 방법이 없다.
    그래서 세션이 첫 override 직전 값을 기억해 두었다가 여기서 되돌린다.
    """
    ax = win.session.fig.axes[0]
    before = [round(v, 4) for v in ax.title.get_position()]
    x, y = center(win, ax.title)
    drag(win.canvas, x, y, x + 40, y + 10)
    assert [round(v, 4) for v in ax.title.get_position()] != before

    win.undo()
    assert win.session.spec.of("ax0.title").get("position") is None
    assert [round(v, 4) for v in ax.title.get_position()] == before


def test_consecutive_undos_each_take_effect(win):
    """연속으로 눌렀을 때 한 번씩 되돌아와야 한다.

    보고된 증상: 몇 번은 먹는 것 같다가 멈추고, 다른 조작을 하면 한꺼번에
    풀린다. 되돌리기가 화면에 반영되지 않아 생기는 착시였다.
    """
    ax = win.session.fig.axes[0]
    orig_title = [round(v, 4) for v in ax.title.get_position()]
    orig_box = [round(v, 4) for v in ax.get_position().bounds]

    x, y = center(win, ax.title)
    drag(win.canvas, x, y, x + 45, y + 10)
    win.canvas.draw()
    # 제목을 옮기면 종이도 다시 맞춰져 축 위치가 함께 바뀐다
    after_title = [round(v, 4) for v in ax.get_position().bounds]

    win.select("ax0")
    bb = ax.get_window_extent()
    drag(win.canvas, bb.x1, (bb.y0 + bb.y1) / 2, bb.x1 - 50, (bb.y0 + bb.y1) / 2)
    win.canvas.draw()
    assert [round(v, 4) for v in ax.get_position().bounds] != after_title

    win.undo()
    assert [round(v, 4) for v in ax.get_position().bounds] == after_title
    win.undo()
    assert [round(v, 4) for v in ax.title.get_position()] == orig_title
    assert [round(v, 4) for v in ax.get_position().bounds] == orig_box


def test_a_legend_drag_is_still_one_undo(win):
    """범례를 끌면 앵커와 함께 loc도 확정된다. 둘이 따로 쌓이면 두 번 눌러야 한다."""
    ax = win.session.fig.axes[0]
    x, y = center(win, ax.get_legend())
    before = len(win.session.history._undo)
    drag(win.canvas, x, y, x - 50, y - 30)
    assert len(win.session.history._undo) - before == 1

    win.undo()
    over = win.session.spec.of("ax0.legend")
    assert over.get("bbox_to_anchor") is None
    assert over.get("loc") is None, "loc 고정이 남으면 범례가 제자리로 안 온다"


def test_redo_puts_it_back(win):
    ax = win.session.fig.axes[0]
    x, y = center(win, ax.title)
    drag(win.canvas, x, y, x + 40, y)
    moved = list(win.session.spec.of("ax0.title")["position"])
    win.undo()
    win.redo()
    assert win.session.spec.of("ax0.title")["position"] == moved
    assert [round(v, 4) for v in ax.title.get_position()] == moved


def test_resetting_a_property_also_restores_the_figure(win):
    """인스펙터의 ↺ 버튼도 같은 길을 쓴다."""
    ax = win.session.fig.axes[0]
    before = round(ax.title.get_fontsize(), 4)
    win.session.set_prop("ax0.title", "fontsize", 22.0)
    assert round(ax.title.get_fontsize(), 4) == 22.0
    win.session.reset_prop("ax0.title", "fontsize")
    assert round(ax.title.get_fontsize(), 4) == before


# --- 커서 ------------------------------------------------------------------

def test_cursor_shows_what_can_be_done(win):
    from PySide6.QtCore import Qt

    ax = win.session.fig.axes[0]
    bb = ax.get_window_extent()
    cases = [
        (center(win, ax.title), Qt.SizeAllCursor),        # 열 십자 — 옮길 수 있다
        (center(win, ax.get_legend()), Qt.SizeAllCursor),
        # 축 본체도 잡아 옮길 수 있다. 한때 화살표였고, 그때는 끌어도 아무
        # 일이 없었으니 정직했다.
        ((bb.x0 + 40, bb.y0 + 25), Qt.SizeAllCursor),
    ]
    for (x, y), want in cases:
        move(win.canvas, x, y)
        assert win.canvas.cursor().shape() == want


def test_selected_box_corner_shows_a_resize_cursor(win):
    from PySide6.QtCore import Qt

    win.select("ax0")
    bb = win.session.fig.axes[0].get_window_extent()
    move(win.canvas, bb.x1, bb.y1)
    assert win.canvas.cursor().shape() == Qt.SizeBDiagCursor
    move(win.canvas, bb.x1, (bb.y0 + bb.y1) / 2)
    assert win.canvas.cursor().shape() == Qt.SizeHorCursor


# --- 판정 지도 캐시 ---------------------------------------------------------

def test_map_is_rebuilt_after_a_redraw(win):
    """다시 그리면 기하가 달라진다. 낡은 지도를 쓰면 클릭이 어긋난다."""
    m = win.canvas.hitmap()
    assert win.canvas.hitmap() is m           # 그리기 전에는 재사용
    win.canvas.draw()
    assert win.canvas.hitmap() is not m


# --- 종이가 따라 커진다 ------------------------------------------------------

def test_dragging_past_the_edge_grows_the_paper(win):
    """종이 밖으로 나간 만큼은 잘려서 보이지 않는다. 잘라내는 대신 키운다."""
    fig = win.session.fig
    before_w = round(fig.get_size_inches()[0], 3)
    win.select("ax1")
    bb = fig.axes[1].get_window_extent()
    drag(win.canvas, bb.x1, (bb.y0 + bb.y1) / 2,
         bb.x1 + 300, (bb.y0 + bb.y1) / 2)
    assert round(fig.get_size_inches()[0], 3) > before_w
    x0, y0, w, h = fig.axes[1].get_position().bounds
    assert x0 + w <= 1 + 1e-6, "키웠는데도 여전히 넘칩니다"


def test_growing_is_part_of_the_same_undo_step(win):
    """따로 쌓이면 실행 취소가 축만 되돌리고 종이는 그대로 둔다."""
    fig = win.session.fig
    before_w = round(fig.get_size_inches()[0], 3)
    steps = len(win.session.history._undo)
    win.select("ax1")
    bb = fig.axes[1].get_window_extent()
    drag(win.canvas, bb.x1, (bb.y0 + bb.y1) / 2,
         bb.x1 + 300, (bb.y0 + bb.y1) / 2)
    assert len(win.session.history._undo) - steps == 1

    win.undo()
    assert round(fig.get_size_inches()[0], 3) == before_w
    assert win.session.spec.of("ax1").get("position") is None


def test_paper_follows_the_content_both_ways(win):
    """좌우도 상하와 똑같이 늘고 줄어야 한다."""
    fig = win.session.fig
    ax = fig.axes[0]
    win.select("ax0")
    bb = ax.get_window_extent()
    before_w = round(fig.get_size_inches()[0], 3)
    drag(win.canvas, bb.x1, (bb.y0 + bb.y1) / 2,
         bb.x1 - 60, (bb.y0 + bb.y1) / 2)          # 좁힌다
    win.canvas.draw()
    assert round(fig.get_size_inches()[0], 3) < before_w


# --- 두 히스토리는 서로를 건드리지 않는다 --------------------------------------

def _toolbar(win):
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
    return win.findChild(NavigationToolbar2QT)


def test_toolbar_back_does_not_undo_a_figtune_edit(win):
    """matplotlib의 내비게이션 스택은 뷰 한계와 함께 축 위치까지 담았다가
    되돌린다. 그대로 두면 툴바의 뒤로가기가 figtune으로 옮긴 축 상자를
    화면에서만 되돌려 놓고, spec은 그대로 남아 화면과 코드가 어긋난다.
    """
    nav = _toolbar(win)
    ax = win.session.fig.axes[0]
    nav.push_current()                       # 사용자가 한 번 확대했다고 치자

    win.select("ax0")
    bb = ax.get_window_extent()
    drag(win.canvas, bb.x1, (bb.y0 + bb.y1) / 2,
         bb.x1 - 60, (bb.y0 + bb.y1) / 2)
    edited = [round(v, 4) for v in win.session.spec.of("ax0")["position"]]

    nav.back()
    win.canvas.draw()
    assert [round(v, 4) for v in ax.get_position().bounds] == edited, \
        "툴바 뒤로가기가 배치를 되돌렸습니다"
    assert [round(v, 4) for v in win.session.spec.of("ax0")["position"]] == edited


def test_toolbar_home_does_not_undo_a_figtune_edit(win):
    nav = _toolbar(win)
    ax = win.session.fig.axes[0]
    nav.push_current()
    win.select("ax0")
    bb = ax.get_window_extent()
    drag(win.canvas, bb.x1, (bb.y0 + bb.y1) / 2,
         bb.x1 - 60, (bb.y0 + bb.y1) / 2)
    edited = [round(v, 4) for v in win.session.spec.of("ax0")["position"]]

    nav.home()
    win.canvas.draw()
    assert [round(v, 4) for v in ax.get_position().bounds] == edited


def test_toolbar_still_restores_the_view(win):
    """배치를 지켰다고 확대·이동까지 못 되돌리면 툴바가 쓸모없어진다."""
    nav = _toolbar(win)
    ax = win.session.fig.axes[0]
    original = [round(v, 3) for v in ax.get_xlim()]
    nav.push_current()
    ax.set_xlim(10, 30)
    nav.push_current()
    nav.back()
    win.canvas.draw()
    assert [round(v, 3) for v in ax.get_xlim()] == original


def test_figtune_undo_is_unaffected_by_the_toolbar(win):
    nav = _toolbar(win)
    ax = win.session.fig.axes[0]
    before = [round(v, 4) for v in ax.get_position().bounds]
    win.select("ax0")
    bb = ax.get_window_extent()
    drag(win.canvas, bb.x1, (bb.y0 + bb.y1) / 2,
         bb.x1 - 60, (bb.y0 + bb.y1) / 2)
    nav.push_current()
    nav.back()
    nav.home()

    win.undo()
    win.canvas.draw()
    assert win.session.spec.of("ax0").get("position") is None
    assert [round(v, 4) for v in ax.get_position().bounds] == before


def test_zoom_alone_never_touches_the_spec(win):
    """확대·이동은 관찰 도구다. 잠깐 둘러본 것까지 기록되면 안 된다."""
    win.session.fig.axes[0].set_xlim(10, 30)
    _toolbar(win).push_current()
    assert win.session.spec.of("ax0").get("xlim") is None
    assert len(win.session.history._undo) == 0


def test_applying_the_view_writes_the_range(win):
    win.session.fig.axes[0].set_xlim(10, 30)
    _toolbar(win).push_current()
    win.apply_view_to_spec()
    assert win.session.spec.of("ax0")["xlim"] == [10.0, 30.0]
    body = win.session.preview_code().split("def apply_style(fig):", 1)[1]
    assert "set_xlim" in body


def test_applying_an_unchanged_view_records_nothing(win):
    """손대지 않은 그림에 xlim이 생기면 '명시된 키만 override'가 깨진다."""
    win.apply_view_to_spec()
    for path in ("ax0", "ax1"):
        assert win.session.spec.of(path).get("xlim") is None
        assert win.session.spec.of(path).get("ylim") is None
    assert len(win.session.history._undo) == 0


def test_applying_the_view_is_one_undo_step(win):
    """패널이 여럿이라 네 값이 바뀌어도 한 칸이다."""
    fig = win.session.fig
    fig.axes[0].set_xlim(10, 30)
    fig.axes[0].set_ylim(1, 2)
    fig.axes[1].set_xlim(0.2, 0.8)
    _toolbar(win).push_current()
    before = len(win.session.history._undo)
    win.apply_view_to_spec()
    assert len(win.session.history._undo) - before == 1

    win.undo()
    for path in ("ax0", "ax1"):
        assert win.session.spec.of(path).get("xlim") is None
        assert win.session.spec.of(path).get("ylim") is None


def test_view_differs_reports_the_state(win):
    assert not win.view_differs()
    win.session.fig.axes[0].set_xlim(10, 30)
    assert win.view_differs()
    win.apply_view_to_spec()
    assert not win.view_differs()


def test_export_leaves_the_exploratory_zoom_out(win, tmp_path):
    """확대한 채로 내보내면 그림에는 확대가 들어가는데 코드에는 없다.
    그 어긋남을 만들지 않으려면 내보낼 때만 spec의 범위로 되돌려야 한다."""
    ax = win.session.fig.axes[0]
    original = [round(v, 3) for v in ax.get_xlim()]
    ax.set_xlim(10, 30)
    _toolbar(win).push_current()

    seen = {}
    real = win.session.export

    def spy(path, **kw):
        seen["xlim"] = [round(v, 3) for v in ax.get_xlim()]
        return real(path, **kw)

    win.session.export = spy
    with win.spec_view() as restored:
        win.session.export(tmp_path / "a.png", dpi=60)
    assert restored is True
    assert seen["xlim"] == original, "내보낼 때 확대가 그대로 들어갔습니다"
    # 내보낸 뒤에는 보던 화면으로 돌아온다
    assert [round(v, 3) for v in ax.get_xlim()] == [10.0, 30.0]


def test_export_is_untouched_when_the_view_matches(win, tmp_path):
    with win.spec_view() as restored:
        pass
    assert restored is False


def test_recording_the_view_does_not_disturb_the_layout(win):
    ax = win.session.fig.axes[0]
    win.select("ax0")
    bb = ax.get_window_extent()
    drag(win.canvas, bb.x1, (bb.y0 + bb.y1) / 2,
         bb.x1 - 60, (bb.y0 + bb.y1) / 2)
    box = list(win.session.spec.of("ax0")["position"])
    ax.set_xlim(10, 30)
    _toolbar(win).push_current()
    assert win.session.spec.of("ax0")["position"] == box


# --- 미니 툴바 --------------------------------------------------------------

def test_clicking_pops_a_mini_toolbar(win):
    """Origin의 결론 — 자주 쓰는 서너 개는 손이 가 있는 자리에서 바로."""
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.get_legend()))
    bar = win.canvas.bar
    assert bar.shown and bar.path == "ax0.legend"
    assert list(bar._rows) == list(__import__(
        "figtune.core.props", fromlist=["P"]).PRIMARY["legend"])


def test_toolbar_is_rebuilt_at_full_size_each_time(win):
    """보이는 상태에서 갈아끼우면 새 위젯이 숨겨진 채로 잡혀 막대가 찌부러진다."""
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.get_legend()))
    first = win.canvas.bar.width()
    tick = next(t for t in ax.get_xticklabels() if t.get_text())
    click(win.canvas, *center(win, tick))
    assert win.canvas.bar.width() > 40, win.canvas.bar.geometry().getRect()
    assert first > 40


def test_toolbar_stays_inside_the_canvas(win):
    ax = win.session.fig.axes[0]
    bb = ax.get_window_extent()
    click(win.canvas, bb.x0 + 4, bb.y1 - 4)          # 구석
    bar = win.canvas.bar
    g = bar.geometry()
    assert g.left() >= 0 and g.top() >= 0
    assert g.right() <= win.canvas.width() and g.bottom() <= win.canvas.height()


def test_editing_from_the_toolbar_reaches_the_spec(win):
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.get_legend()))
    win.canvas.bar.edited.emit("ax0.legend", "frameon", False)
    assert win.session.spec.of("ax0.legend")["frameon"] is False


def test_toolbar_hides_once_dragging_starts(win):
    """누르는 순간 치우면 끌지 않고 고르기만 해도 사라진다."""
    ax = win.session.fig.axes[0]
    x, y = center(win, ax.get_legend())
    press(win.canvas, x, y)
    assert win.canvas.bar.shown, "누르자마자 사라졌습니다"
    move(win.canvas, x - 40, y - 20)
    assert not win.canvas.bar.shown
    release(win.canvas, x - 40, y - 20)


def test_toolbar_comes_back_after_a_drag(win):
    ax = win.session.fig.axes[0]
    x, y = center(win, ax.get_legend())
    drag(win.canvas, x, y, x - 40, y - 20)
    assert win.canvas.bar.shown


# --- 탭 대화상자 ------------------------------------------------------------

def test_double_click_on_an_axis_opens_every_part(win):
    """Origin의 Axis Dialog — 눈금·축선·격자·범위가 한 화면에 온다."""
    ax = win.session.fig.axes[0]
    tick = next(t for t in ax.get_xticklabels() if t.get_text())
    x, y = center(win, tick)
    press(win.canvas, x, y, dbl=True)
    dlg = win.canvas._dialog
    assert dlg is not None
    assert dlg.tabs.count() == 5
    assert win.canvas._target.scope() == (
        "ax0.xtick.major", "ax0.xtick.minor", "ax0.spine:bottom",
        "ax0.grid.x", "ax0")
    dlg.close()


def test_dialog_edits_reach_the_spec(win):
    ax = win.session.fig.axes[0]
    tick = next(t for t in ax.get_xticklabels() if t.get_text())
    press(win.canvas, *center(win, tick), dbl=True)
    dlg = win.canvas._dialog
    dlg.edited.emit("ax0.grid.x", "visible", True)
    assert win.session.spec.of("ax0.grid.x")["visible"] is True
    dlg.close()


def test_dialog_reset_restores_the_figure(win):
    ax = win.session.fig.axes[0]
    win.session.set_prop("ax0.title", "fontsize", 22.0)
    press(win.canvas, *center(win, ax.title), dbl=True)
    dlg = win.canvas._dialog
    dlg.reset.emit("ax0.title", "fontsize")
    assert win.session.spec.of("ax0.title").get("fontsize") is None
    dlg.close()


def test_double_click_does_not_open_the_caret(win):
    """더블클릭은 전체 편집기다. 캐럿이 함께 뜨면 둘이 겹친다."""
    ax = win.session.fig.axes[0]
    press(win.canvas, *center(win, ax.title), dbl=True)
    assert not win.canvas.editor.active
    assert win.canvas._dialog is not None
    win.canvas._dialog.close()


# --- 선택 표시 --------------------------------------------------------------

def test_selection_draws_a_box_around_the_target(win):
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.title))
    assert win.canvas.highlights()
    _path, _x, _y, w, h = win.canvas.highlights()[0]
    assert w > 0 and h > 0


def test_highlight_follows_the_exact_target_not_just_the_path(win):
    """위·아래 축선은 둘 다 'x축'이라 path가 같다. 합치면 테두리가 상자
    세로 전체를 덮어 무엇을 골랐는지 알 수 없어진다."""
    ax = win.session.fig.axes[0]
    tick = next(t for t in ax.get_xticklabels() if t.get_text())
    click(win.canvas, *center(win, tick))
    _path, _x, _y, _w, h = win.canvas.highlights()[0]
    box_h = ax.get_window_extent().height
    assert h < box_h / 2, "테두리가 축 상자 전체를 덮었습니다"


def test_clearing_the_selection_clears_the_box(win):
    win.select("ax0.title")
    assert win.canvas.highlights()
    win.select(None)
    assert not win.canvas.highlights()
    assert not win.canvas.bar.shown


def test_highlight_is_not_a_figure_artist(win):
    """matplotlib artist로 그리면 내보낸 그림에까지 테두리가 따라 들어간다."""
    before = sum(len(ax.patches) for ax in win.session.fig.axes)
    win.select("ax0")
    win.canvas.draw()
    after = sum(len(ax.patches) for ax in win.session.fig.axes)
    assert after == before


# --- 색 견본 ----------------------------------------------------------------

def test_swatch_text_is_readable_on_any_background():
    """견본에 hex를 찍는데 글자색을 고정하면 어두운 색에서 검정 위 검정이
    되어 아무것도 안 보인다. 검은 눈금이 기본값이라 흔히 걸린다."""
    from figtune.ui.qt.widgets import contrasting_text

    assert contrasting_text("#000000") == "#ffffff"
    assert contrasting_text("#ffffff") == "#000000"
    assert contrasting_text("#00008b") == "#ffffff"      # 어두운 파랑
    assert contrasting_text("#ffff00") == "#000000"      # 밝은 노랑


def test_swatch_handles_names_and_garbage():
    from figtune.ui.qt.widgets import contrasting_text

    assert contrasting_text("red") in ("#000000", "#ffffff")
    assert contrasting_text("이건 색이 아니다") == "#000000"


def test_swatch_style_does_not_leak_into_the_colour_dialog(qapp):
    """스타일시트는 자식 위젯으로 번진다. 이 버튼을 부모로 삼는 색 선택
    대화상자까지 검은 배경을 물려받아 글자가 하나도 안 보이게 된다."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    from figtune.ui.qt.widgets import ColorButton

    btn = ColorButton("#000000")
    dlg = QColorDialog(QColor("#000000"), btn)
    dlg.setOption(QColorDialog.DontUseNativeDialog, True)
    try:
        assert dlg.palette().window().color().name() != "#000000"
    finally:
        dlg.deleteLater()
        btn.deleteLater()


def test_swatch_stylesheet_is_scoped_to_itself(qapp):
    from figtune.ui.qt.widgets import ColorButton

    btn = ColorButton("#2ca02c")
    assert btn.styleSheet().startswith(f"QPushButton#{ColorButton.OBJECT_NAME}")
    btn.deleteLater()


# --- Esc로 놓기 -------------------------------------------------------------

def _escape(widget):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    widget.keyPressEvent(
        QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))


def test_escape_clears_the_whole_selection(win):
    """그림만 보고 싶을 때 막대·테두리가 겹쳐 있으면 거슬린다."""
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.get_legend()))
    assert win.canvas.bar.shown and win.canvas.highlights()

    _escape(win.canvas)
    assert not win.canvas.bar.shown
    assert not win.canvas.highlights()
    assert win._current is None


def test_escape_clears_the_tree_selection_too(win):
    """하나만 지우면 화면마다 다른 것을 고른 것처럼 보인다."""
    win.select("ax0.title")
    win._sync_tree_selection("ax0.title")
    assert win.tree.selectedItems()
    _escape(win.canvas)
    assert not win.tree.selectedItems()


def test_escape_inside_the_toolbar_also_clears(win):
    """막대 입력칸에 포커스가 있으면 캔버스는 Esc를 받지 못한다."""
    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.get_legend()))
    _escape(win.canvas.bar)
    assert not win.canvas.bar.shown
    assert win._current is None


def test_escape_while_editing_cancels_the_edit_first(win):
    """편집 중 Esc는 글자를 되돌리는 것이지 선택을 푸는 것이 아니다."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    ax = win.session.fig.axes[0]
    click(win.canvas, *center(win, ax.title))
    assert win.canvas.editor.active
    win.canvas.editor.setText("망친 제목")
    win.canvas.editor.keyPressEvent(
        QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    assert not win.canvas.editor.active
    assert ax.title.get_text() == "Uptake"
    assert win._current == "ax0.title", "편집 취소가 선택까지 풀었습니다"


def test_escape_with_nothing_selected_is_harmless(win):
    _escape(win.canvas)
    assert win._current is None


def test_apply_range_button_lives_next_to_the_zoom_tools(win):
    """확대는 툴바에서 한다. 남기는 버튼이 메뉴에만 있으면 찾지 못한다."""
    assert win.apply_view_act in _toolbar(win).actions()


def test_apply_range_button_is_off_until_there_is_something_to_apply(win):
    assert not win.apply_view_act.isEnabled()
    win.session.fig.axes[0].set_xlim(10, 30)
    _toolbar(win).push_current()
    assert win.apply_view_act.isEnabled()


def test_apply_range_button_turns_off_after_applying(win):
    win.session.fig.axes[0].set_xlim(10, 30)
    _toolbar(win).push_current()
    win.apply_view_act.trigger()
    assert not win.apply_view_act.isEnabled()
    assert win.session.spec.of("ax0")["xlim"] == [10.0, 30.0]


def test_apply_range_button_comes_back_after_undo(win):
    win.session.fig.axes[0].set_xlim(10, 30)
    _toolbar(win).push_current()
    win.apply_view_act.trigger()
    win.undo()
    assert win.apply_view_act.isEnabled()


def test_paper_returns_when_the_title_comes_back_down(win):
    """보고된 증상: 제목을 올렸다 내렸는데 흰 영역이 커진 채로 남았다."""
    fig = win.session.fig
    ax = fig.axes[0]
    x, y = center(win, ax.title)
    drag(win.canvas, x, y, x, y + 3)               # 한 번 맞춰 놓는다
    win.canvas.draw()
    settled = round(fig.get_size_inches()[1], 2)

    x, y = center(win, ax.title)
    drag(win.canvas, x, y, x, y + 130)
    win.canvas.draw()
    assert round(fig.get_size_inches()[1], 2) > settled

    x, y = center(win, ax.title)
    drag(win.canvas, x, y, x, y - 130)
    win.canvas.draw()
    assert round(fig.get_size_inches()[1], 2) == pytest.approx(settled, abs=0.1)


def test_paper_can_shrink_below_the_original(win):
    """제목이 처음보다 낮아지면 처음보다 줄어야 한다."""
    fig = win.session.fig
    ax = fig.axes[0]
    start = round(fig.get_size_inches()[1], 2)
    x, y = center(win, ax.title)
    drag(win.canvas, x, y, x, y - 40)
    win.canvas.draw()
    assert round(fig.get_size_inches()[1], 2) < start


def test_unconverged_growth_is_reported(win, monkeypatch):
    """3번 안에 수렴하지 못하면 종이가 몇 mm 모자란 채 남는다.

    조용히 끝내면 사용자는 그것이 최종 상태인지 도구가 포기한 상태인지
    구분할 수 없다. 잘린 글자를 보고도 원인을 짚을 방법이 없다.
    """
    seen = []
    monkeypatch.setattr(type(win), "status",
                        lambda self, msg: seen.append(msg))
    monkeypatch.setattr(type(win.canvas), "GROW_PASSES", 0)

    fig = win.session.fig
    win.select("ax1")
    bb = fig.axes[1].get_window_extent()
    drag(win.canvas, bb.x1, (bb.y0 + bb.y1) / 2,
         bb.x1 + 300, (bb.y0 + bb.y1) / 2)

    assert any("종이" in m for m in seen), \
        f"수렴 실패를 알리지 않았습니다: {seen}"


def test_converged_growth_is_silent(win, monkeypatch):
    """맞춰졌으면 아무 말도 하지 않아야 한다. 늘 경고하면 경고가 안 읽힌다."""
    seen = []
    monkeypatch.setattr(type(win), "status",
                        lambda self, msg: seen.append(msg))

    fig = win.session.fig
    win.select("ax1")
    bb = fig.axes[1].get_window_extent()
    drag(win.canvas, bb.x1, (bb.y0 + bb.y1) / 2,
         bb.x1 + 60, (bb.y0 + bb.y1) / 2)

    assert not any("맞추지 못했습니다" in m for m in seen), seen


# --- usertext도 같은 끌기다 --------------------------------------------------

def _add_note(win, position=(0.5, 0.5)):
    tid = win.session.add_text(0, "note", position)
    win.canvas.draw()
    art = next(t for t in win.session.fig.axes[0].texts
               if getattr(t, "_figtune_id", None) == tid)
    return tid, art


def test_dragging_a_usertext_is_one_undo_step(win):
    """한때 usertext 끌기는 히스토리에 아무것도 남기지 않았다.

    실행 취소를 누르면 그 이동을 건너뛰고 그 전의 편집이 되돌아갔다.
    사용자 눈에는 실행 취소가 엉뚱한 것을 되돌리는 것으로 보인다.
    """
    _, art = _add_note(win)
    before = [round(v, 4) for v in art.get_position()]
    steps = len(win.session.history._undo)

    x, y = center(win, art)
    drag(win.canvas, x, y, x + 80, y)
    assert len(win.session.history._undo) - steps == 1
    assert [round(v, 4) for v in art.get_position()] != before

    win.undo()
    assert [round(v, 4) for v in art.get_position()] == before


def test_dragging_a_usertext_does_not_jump(win):
    """글자 왼쪽 끝을 잡아도 앵커가 커서 밑으로 순간이동하면 안 된다."""
    _, art = _add_note(win)
    before = art.get_position()
    bb = art.get_window_extent(win.canvas.get_renderer())
    grab_x, grab_y = bb.x0 + 2, (bb.y0 + bb.y1) / 2

    press(win.canvas, grab_x, grab_y)
    move(win.canvas, grab_x + 40, grab_y)
    move(win.canvas, grab_x, grab_y)          # 잡은 자리로 되돌아온다
    release(win.canvas, grab_x, grab_y)

    now = art.get_position()
    assert now[0] == pytest.approx(before[0], abs=1e-3)
    assert now[1] == pytest.approx(before[1], abs=1e-3)


def test_dragging_a_usertext_refits_the_paper(win):
    """다른 끌기와 같이 종이가 따라와야 한다. 아니면 글자가 잘린 채 남는다.

    '커진다'가 아니라 '맞춰진다'이다. 종이는 내용의 경계 + 여백이므로,
    같은 끌기에 처음의 남는 여백이 함께 정리되면 오히려 줄어들 수 있다.
    """
    _, art = _add_note(win)
    fig = win.session.fig
    before = tuple(round(v, 3) for v in fig.get_size_inches())

    x, y = center(win, art)
    drag(win.canvas, x, y, x + 400, y)

    assert tuple(round(v, 3) for v in fig.get_size_inches()) != before, \
        "종이가 전혀 맞춰지지 않았습니다"
    edge = art.get_window_extent(win.canvas.get_renderer()).x1
    assert edge <= fig.get_window_extent().x1 + 1, "글자가 종이 밖에 남았습니다"


def test_mini_toolbar_returns_after_a_usertext_drag(win):
    """끌기가 끝나면 막대를 다시 내준다 — 이어서 손볼 것이 있게 마련이다."""
    _, art = _add_note(win)
    x, y = center(win, art)
    drag(win.canvas, x, y, x + 80, y)
    assert win.canvas.bar.shown


# --- 축 본체를 끌어 옮긴다 ---------------------------------------------------

def test_dragging_the_plot_area_moves_the_axes(win):
    """도형을 잡아 끌면 옮겨지는 것이 캔버스의 기본 기대다.

    축은 크기만 바뀌고 이동이 안 돼서, 사용자는 '왜 이것만 안 되지'를
    매번 겪었다.
    """
    fig = win.session.fig

    def size_in_inches():
        # 축 상자는 figure 비율이다. 종이가 다시 맞춰지면 물리 크기가 같아도
        # 비율은 바뀌므로, 크기 비교는 인치로 해야 뜻이 있다.
        _x, _y, w, h = fig.axes[0].get_position().bounds
        fw, fh = (float(v) for v in fig.get_size_inches())
        return round(float(w * fw), 3), round(float(h * fh), 3)

    ax = fig.axes[0]
    before_x = round(float(ax.get_position().bounds[0]), 4)
    before_size = size_in_inches()
    bb = ax.get_window_extent()
    x, y = bb.x0 + 40, bb.y0 + 25

    drag(win.canvas, x, y, x + 50, y)
    assert round(float(ax.get_position().bounds[0]), 4) > before_x, \
        "축이 오른쪽으로 가지 않았습니다"
    assert size_in_inches() == before_size, "크기가 함께 변했습니다"


def test_moving_the_axes_is_one_undo_step(win):
    ax = win.session.fig.axes[0]
    before = [round(float(v), 4) for v in ax.get_position().bounds]
    steps = len(win.session.history)
    bb = ax.get_window_extent()
    x, y = bb.x0 + 40, bb.y0 + 25

    drag(win.canvas, x, y, x + 50, y)
    assert len(win.session.history) - steps == 1
    win.undo()
    assert [round(float(v), 4) for v in ax.get_position().bounds] == before


def test_pan_mode_does_not_move_the_axes(win):
    """확대·이동은 관찰 도구다 — spec을 건드리면 안 된다.

    가드가 없으면 pan 중에 화면도 움직이고 축도 옮겨져, 툴바로 들여다본
    것만으로 그림의 배치가 바뀐다.
    """
    ax = win.session.fig.axes[0]
    before = [round(float(v), 4) for v in ax.get_position().bounds]
    win.toolbar.pan()
    try:
        bb = ax.get_window_extent()
        x, y = bb.x0 + 40, bb.y0 + 25
        drag(win.canvas, x, y, x + 50, y)
        assert [round(float(v), 4) for v in ax.get_position().bounds] == before
        assert win.session.spec.of("ax0").get("position") is None
    finally:
        win.toolbar.pan()


def test_pan_mode_leaves_the_cursor_to_the_toolbar(win):
    """확대·이동 중에 편집 커서를 덮으면 할 수 있는 일을 잘못 알린다."""
    from PySide6.QtCore import Qt

    ax = win.session.fig.axes[0]
    bb = ax.get_window_extent()
    win.canvas.setCursor(Qt.ArrowCursor)
    win.toolbar.pan()
    try:
        move(win.canvas, bb.x0 + 40, bb.y0 + 25)
        assert win.canvas.cursor().shape() != Qt.SizeAllCursor
    finally:
        win.toolbar.pan()


# --- 다중 선택 ---------------------------------------------------------------
#
# PowerPoint는 도형 선택에서 Shift와 Ctrl을 같게 다룬다 — 어느 쪽이든
# 토글-추가다. 둘이 갈리는 것은 끌기(복제 vs 축 고정)와 목록에서다.
# 그래서 캔버스는 둘을 같게 두고, 범위 선택은 트리가 맡는다.

def add_click(c, x, y, key="shift"):
    c._press(MouseEvent("button_press_event", c, x, y, 1, key=key))
    c._release(MouseEvent("button_release_event", c, x, y, 1, key=key))


@pytest.mark.parametrize("key", ["shift", "control"])
def test_modifier_click_adds_to_the_selection(win, key):
    fig = win.session.fig
    click(win.canvas, *center(win, fig.axes[0].title))
    assert win.selection() == ["ax0.title"]

    add_click(win.canvas, *center(win, fig.axes[1].title), key=key)
    assert win.selection() == ["ax0.title", "ax1.title"]


@pytest.mark.parametrize("key", ["shift", "control"])
def test_modifier_click_on_a_selected_one_removes_it(win, key):
    """PowerPoint와 같이 토글이다. 뺄 방법이 없으면 잘못 고른 것을 되돌리려고
    처음부터 다시 골라야 한다."""
    fig = win.session.fig
    click(win.canvas, *center(win, fig.axes[0].title))
    add_click(win.canvas, *center(win, fig.axes[1].title), key=key)
    add_click(win.canvas, *center(win, fig.axes[1].title), key=key)
    assert win.selection() == ["ax0.title"]


def test_plain_click_replaces_the_selection(win):
    fig = win.session.fig
    click(win.canvas, *center(win, fig.axes[0].title))
    add_click(win.canvas, *center(win, fig.axes[1].title))
    click(win.canvas, *center(win, fig.axes[1].title))
    assert win.selection() == ["ax1.title"]


def test_clearing_drops_every_selected_element(win):
    fig = win.session.fig
    click(win.canvas, *center(win, fig.axes[0].title))
    add_click(win.canvas, *center(win, fig.axes[1].title))
    win.clear_selection()
    assert win.selection() == []


def test_every_selected_element_is_outlined(win):
    """하나만 테두리가 뜨면 무엇이 고쳐질지 알 수 없다."""
    fig = win.session.fig
    click(win.canvas, *center(win, fig.axes[0].title))
    add_click(win.canvas, *center(win, fig.axes[1].title))
    assert len(win.canvas.highlights()) == 2


def test_handles_are_suppressed_while_multiple_are_selected(win):
    """여러 개를 고른 채 핸들이 살아 있으면 무엇의 크기가 바뀔지 모호하다."""
    win.select("ax0")
    bb = win.session.fig.axes[0].get_window_extent()
    assert win.canvas.targets_at(
        MouseEvent("motion_notify_event", win.canvas, bb.x1, bb.y1, None))

    win.select_paths(["ax0", "ax1"])
    ts = win.canvas.targets_at(
        MouseEvent("motion_notify_event", win.canvas, bb.x1, bb.y1, None))
    assert not [t for t in ts if t.kind == "resize"]


def test_tree_allows_range_and_toggle_selection(win):
    """트리는 목록이다 — Shift 범위와 Ctrl 개별이 사는 곳은 여기다."""
    from PySide6.QtWidgets import QAbstractItemView

    assert win.tree.selectionMode() == QAbstractItemView.ExtendedSelection


def test_tree_multi_selection_reaches_the_window(win):
    from PySide6.QtCore import Qt

    items = win.tree.findItems("", Qt.MatchContains | Qt.MatchRecursive, 0)
    picks = [it for it in items
             if it.data(0, Qt.UserRole) in ("ax0.title", "ax1.title")]
    assert len(picks) == 2
    for it in picks:
        it.setSelected(True)
    assert sorted(win.selection()) == ["ax0.title", "ax1.title"]


# --- 교집합 properties -------------------------------------------------------

def _labels(win):
    return {name: prop.label for name, (prop, _w) in win.inspector._rows.items()}


def test_inspector_shows_only_shared_properties(win):
    win.select_paths(["ax0.line0", "ax0.spine:top"])
    names = set(win.inspector._rows)
    assert {"color", "linewidth"} <= names
    assert "marker" not in names, "선에만 있는 속성이 떴습니다"


def test_inspector_uses_the_shorter_label(win):
    win.select_paths(["ax0.line0", "ax0.spine:top"])
    assert _labels(win)["linewidth"] == "두께"


def test_editing_applies_to_every_selected(win):
    win.select_paths(["ax0.line0", "ax0.line1"])
    win.inspector.edited.emit("linewidth", 3.5)
    assert win.session.spec.get("ax0.line0", "linewidth") == 3.5
    assert win.session.spec.get("ax0.line1", "linewidth") == 3.5


def test_editing_many_is_one_undo_step(win):
    win.select_paths(["ax0.line0", "ax0.line1"])
    steps = len(win.session.history)
    win.inspector.edited.emit("linewidth", 3.5)
    assert len(win.session.history) - steps == 1
    win.undo()
    assert win.session.spec.get("ax0.line0", "linewidth") is None
    assert win.session.spec.get("ax0.line1", "linewidth") is None


def test_differing_values_are_not_invented(win):
    """값이 갈리는 칸에 아무 값이나 채우면, 그것이 현재 값인 줄 알고
    넘어가서 건드리지 않은 대상까지 그 값으로 덮인다."""
    win.session.set_prop("ax0.line0", "linewidth", 1.0)
    win.session.set_prop("ax0.line1", "linewidth", 4.0)
    win.select_paths(["ax0.line0", "ax0.line1"])
    _vals, mixed, _over = win._shared_values(["ax0.line0", "ax0.line1"])
    assert "linewidth" in mixed

    # 고르기만 해서는 아무것도 바뀌지 않는다
    assert win.session.spec.get("ax0.line0", "linewidth") == 1.0
    assert win.session.spec.get("ax0.line1", "linewidth") == 4.0


def test_equal_values_are_shown_as_the_common_one(win):
    win.session.set_prop("ax0.line0", "linewidth", 2.0)
    win.session.set_prop("ax0.line1", "linewidth", 2.0)
    vals, mixed, _over = win._shared_values(["ax0.line0", "ax0.line1"])
    assert vals["linewidth"] == 2.0 and "linewidth" not in mixed


def test_reset_clears_the_override_on_every_selected(win):
    win.select_paths(["ax0.line0", "ax0.line1"])
    win.inspector.edited.emit("linewidth", 3.5)
    win.inspector.reset.emit("linewidth")
    assert win.session.spec.get("ax0.line0", "linewidth") is None
    assert win.session.spec.get("ax0.line1", "linewidth") is None


def test_mixed_kinds_still_share_the_basics(win):
    """선과 격자를 함께 골라도 색과 두께는 함께 바꿀 수 있어야 한다."""
    win.select_paths(["ax0.line0", "ax0.grid.x"])
    assert {"color", "linewidth", "linestyle"} <= set(win.inspector._rows)
    win.inspector.edited.emit("color", "#123456")
    assert win.session.spec.get("ax0.line0", "color") == "#123456"
    assert win.session.spec.get("ax0.grid.x", "color") == "#123456"


# --- 여럿을 통째로 옮긴다 -----------------------------------------------------

def test_dragging_moves_every_selected_axes(win, tmp_path, qapp):
    """PowerPoint처럼 고른 것이 다 함께 따라와야 한다.

    잡은 것 하나만 움직이면, 여러 개를 고른 것이 무의미해지고 나머지를
    같은 거리만큼 손으로 맞춰야 한다.

    절대 위치로는 가릴 수 없다 — 종이 맞추기가 축들을 다시 배치하므로
    따라오지 않아도 값이 변한다. 같은 끌기를 하나만 고른 채로도 해 보고
    ax1이 다른 자리에 놓이는지를 본다.
    """
    import shutil

    from figtune.ui.qt.main import MainWindow

    def run(paths):
        script = tmp_path / f"{len(paths)}.py"
        shutil.copy(EXAMPLE, script)
        w = MainWindow(script)
        w.canvas.draw()
        w.select_paths(paths)
        bb = w.session.fig.axes[0].get_window_extent()
        x, y = bb.x0 + 40, bb.y0 + 25
        drag(w.canvas, x, y, x, y + 30)          # 위로
        got = [round(float(v), 4)
               for v in w.session.fig.axes[1].get_position().bounds]
        w.close()
        return got

    alone = run(["ax0"])
    together = run(["ax0", "ax1"])
    assert alone != together, "함께 고른 축이 따라오지 않았습니다"


def test_moving_many_is_one_undo_step(win):
    fig = win.session.fig
    win.select_paths(["ax0", "ax1"])
    steps = len(win.session.history)
    bb = fig.axes[0].get_window_extent()
    x, y = bb.x0 + 40, bb.y0 + 25
    drag(win.canvas, x, y, x, y + 30)
    assert len(win.session.history) - steps == 1

    win.undo()
    assert win.session.spec.of("ax0").get("position") is None
    assert win.session.spec.of("ax1").get("position") is None


def test_they_move_by_the_same_amount(win):
    """따라오는 것이 다른 거리를 가면 상대 배치가 무너진다."""
    fig = win.session.fig
    win.select_paths(["ax0", "ax1"])
    before = [float(ax.get_position().bounds[1]) for ax in fig.axes]
    fh = float(fig.get_size_inches()[1])
    before_in = [b * fh for b in before]

    bb = fig.axes[0].get_window_extent()
    x, y = bb.x0 + 40, bb.y0 + 25
    drag(win.canvas, x, y, x, y + 30)

    fh2 = float(fig.get_size_inches()[1])
    now_in = [float(ax.get_position().bounds[1]) * fh2 for ax in fig.axes]
    deltas = [round(n - b, 3) for n, b in zip(now_in, before_in)]
    assert deltas[0] != 0, "아예 움직이지 않았습니다"
    assert deltas[0] == deltas[1], f"서로 다른 거리를 갔습니다: {deltas}"


def test_dragging_an_unselected_one_drops_the_selection(win):
    """고르지 않은 것을 잡으면 그것 하나를 고른 것이다 — PowerPoint와 같다."""
    fig = win.session.fig
    win.select_paths(["ax0", "ax0.title"])
    x, y = center(win, fig.axes[1].title)
    drag(win.canvas, x, y, x + 40, y)
    assert win.selection() == ["ax1.title"]
    # ax0가 아니라 ax0.title로 본다 — 축 위치는 종이를 다시 맞추면서
    # 어차피 다시 잡히므로, 따라 움직였는지를 가려내지 못한다.
    assert win.session.spec.of("ax0.title").get("position") is None


def test_mixed_kinds_move_together(win):
    """축과 제목을 함께 골라도 둘 다 따라와야 한다."""
    fig = win.session.fig
    win.select_paths(["ax0", "ax0.title"])
    bb = fig.axes[0].get_window_extent()
    x, y = bb.x0 + 40, bb.y0 + 25
    drag(win.canvas, x, y, x + 40, y)
    assert win.session.spec.of("ax0").get("position") is not None
    assert win.session.spec.of("ax0.title").get("position") is not None


# --- 삭제 --------------------------------------------------------------------

def test_delete_action_is_off_without_a_selection(win):
    win.select(None)
    assert not win.delete_act.isEnabled()


def test_delete_action_is_off_for_script_owned_things(win):
    """원본이 만든 것은 지워도 재실행하면 되살아난다. 버튼이 살아 있으면
    지워지는 줄 알고 눌렀다가 돌아오는 것을 보게 된다."""
    for path in ("ax0.title", "ax0.line0", "ax0"):
        win.select(path)
        assert not win.delete_act.isEnabled(), path


def test_delete_action_wakes_for_figtune_owned_text(win):
    tid = win.session.add_text(0, "mine")
    win.reload_tree()
    win.select(sel_usertext(0, tid))
    assert win.delete_act.isEnabled()


def test_delete_removes_it_and_refreshes_the_tree(win):
    tid = win.session.add_text(0, "mine")
    win.reload_tree()
    path = sel_usertext(0, tid)
    win.select(path)
    win.delete_selection()

    assert win.session.spec.text_by_id(tid) is None
    assert path not in _tree_paths(win)
    assert win.selection() == []


def test_the_delete_key_deletes(win):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    tid = win.session.add_text(0, "mine")
    win.reload_tree()
    win.select(sel_usertext(0, tid))
    win.canvas.keyPressEvent(
        QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
    assert win.session.spec.text_by_id(tid) is None


def test_the_delete_key_leaves_script_owned_things_alone(win):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    ax = win.session.fig.axes[0]
    before = ax.title.get_text()
    win.select("ax0.title")
    win.canvas.keyPressEvent(
        QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
    assert ax.title.get_text() == before


def test_deleting_several_is_one_undo_step(win):
    ids = [win.session.add_text(0, f"t{i}") for i in range(3)]
    win.reload_tree()
    win.select_paths([sel_usertext(0, t) for t in ids])
    steps = len(win.session.history)

    win.delete_selection()
    assert len(win.session.history) - steps == 1
    win.undo()
    assert all(win.session.spec.text_by_id(t) is not None for t in ids)


def test_deleting_while_editing_text_does_not_fire(win):
    """캐럿이 떠 있으면 Delete는 글자 지우기다 — 요소를 지우면 안 된다."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    tid = win.session.add_text(0, "mine")
    win.reload_tree()
    win.select(sel_usertext(0, tid))
    art = next(t for t in win.session.fig.axes[0].texts
               if getattr(t, "_figtune_id", None) == tid)
    win.canvas.editor.open_at(sel_usertext(0, tid), art, click_x=0)
    win.canvas.keyPressEvent(
        QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
    assert win.session.spec.text_by_id(tid) is not None


# --- 붙기(snap) ---------------------------------------------------------------

def _box(win, path):
    """artist에서 직접 잰다.

    canvas._box_for는 판정 지도 캐시를 먼저 보는데, 그 캐시는 다시 그릴 때만
    갱신된다. 테스트에는 이벤트 루프가 없어 draw_idle이 처리되지 않으므로
    끌기 도중에는 끌기 전 값이 나온다.
    """
    from figtune.core import selector as sel
    art = sel.resolve(win.session.fig, path)
    bb = art.get_window_extent(win.canvas.get_renderer())
    return (bb.x0, bb.y0, bb.x1, bb.y1)


def _drag_hold(c, x0, y0, x1, y1):
    """떼지 않고 끄는 중까지만. 종이 맞추기는 뗄 때 일어나므로, 화면
    좌표로 무언가를 재려면 그 전에 재야 한다."""
    press(c, x0, y0)
    move(c, x1, y1)


def test_dragging_snaps_to_another_element(win):
    """눈으로 맞춘 정렬은 1~2픽셀씩 어긋난다. 인쇄하면 보인다.

    어느 정렬에 붙을지는 미리 알 수 없다 — 모서리끼리가 가까울 수도,
    가운데끼리가 가까울 수도 있다. 확인할 것은 '붙었으면 정확히 맞는다'다.
    """
    fig = win.session.fig
    target_left = _box(win, "ax1.title")[0]
    left = _box(win, "ax0.title")[0]
    x, y = center(win, fig.axes[0].title)

    _drag_hold(win.canvas, x, y, x + (target_left - left) - 3, y)
    box = _box(win, "ax0.title")
    guides = [g for g in win.canvas.guides() if g.axis == "x"]
    release(win.canvas, x + (target_left - left) - 3, y)

    assert guides, "붙지 않았습니다"
    lines = (box[0], (box[0] + box[2]) / 2, box[2])
    assert min(abs(v - guides[0].at) for v in lines) < 0.01, \
        f"안내선 {guides[0].at}에 정확히 맞지 않았습니다: {lines}"


def test_a_far_drop_is_left_alone(win):
    """임계값 밖에서는 원하는 자리에 그대로 놓여야 한다."""
    fig = win.session.fig
    left = _box(win, "ax0.title")[0]
    x, y = center(win, fig.axes[0].title)
    _drag_hold(win.canvas, x, y, x + 40, y)
    moved = _box(win, "ax0.title")[0] - left
    release(win.canvas, x + 40, y)
    assert 38 < moved < 42, moved


def test_guides_appear_while_snapped_and_go_when_dropped(win):
    """무엇에 붙었는지 보이지 않으면 왜 튀었는지 알 수 없다."""
    fig = win.session.fig
    target_left = _box(win, "ax1.title")[0]
    left = _box(win, "ax0.title")[0]
    x, y = center(win, fig.axes[0].title)

    press(win.canvas, x, y)
    move(win.canvas, x + (target_left - left) - 3, y)
    assert win.canvas.guides(), "안내선이 없습니다"
    release(win.canvas, x + (target_left - left) - 3, y)
    assert not win.canvas.guides(), "떼었는데 안내선이 남았습니다"


def test_alt_turns_snapping_off(win, monkeypatch):
    """수식키를 누르면 원하는 자리에 정확히 둘 수 있어야 한다."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(QApplication, "keyboardModifiers",
                        staticmethod(lambda: Qt.AltModifier))
    fig = win.session.fig
    target_left = _box(win, "ax1.title")[0]
    left = _box(win, "ax0.title")[0]
    x, y = center(win, fig.axes[0].title)

    _drag_hold(win.canvas, x, y, x + (target_left - left) - 3, y)
    now = _box(win, "ax0.title")[0]
    release(win.canvas, x + (target_left - left) - 3, y)
    assert abs(now - (target_left - 3)) < 1.5, f"붙어 버렸습니다: {now}"


def test_the_thing_being_dragged_is_not_its_own_target(win):
    """자기 자신에게 붙으면 끌기가 그 자리에 얼어붙는다."""
    fig = win.session.fig
    left = _box(win, "ax0.title")[0]
    x, y = center(win, fig.axes[0].title)
    _drag_hold(win.canvas, x, y, x + 25, y)
    now = _box(win, "ax0.title")[0]
    release(win.canvas, x + 25, y)
    assert now > left + 15, f"제자리에 얼어붙었습니다: {left} -> {now}"


# --- 범례: 이름 있는 위치를 고르면 그리로 간다 ---------------------------------
#
# 끌면 bbox_to_anchor가 생긴다. 그것이 남아 있으면 loc은 '축의 어디'가 아니라
# '앵커점에 범례의 어느 모서리를 맞출지'만 정한다. 그래서 'upper left'를
# 골라도 좌상단으로 가지 않는다 — 고른 대로 되지 않는 조용한 무동작이다.
#
# 드롭다운은 거친 배치, 끌기는 자유 배치. 각 제스처가 결과를 온전히 정한다.

def _legend_corner(win):
    ax = win.session.fig.axes[0]
    bb = ax.get_legend().get_window_extent(win.canvas.get_renderer())
    a = ax.get_window_extent()
    return ((bb.x0 - a.x0) / a.width, (bb.y1 - a.y0) / a.height)


def test_choosing_a_named_position_moves_it_there(win):
    ax = win.session.fig.axes[0]
    x, y = center(win, ax.get_legend())
    drag(win.canvas, x, y, x - 60, y - 60)          # 앵커가 생긴다
    assert win.session.spec.of("ax0.legend").get("bbox_to_anchor") is not None

    win.select("ax0.legend")
    win.inspector.edited.emit("loc", "upper left")
    win.session.fig.canvas.draw()

    assert win.session.spec.of("ax0.legend").get("bbox_to_anchor") is None
    cx, cy = _legend_corner(win)
    assert cx < 0.1 and cy > 0.9, f"좌상단으로 가지 않았습니다: {cx, cy}"


def test_dragging_still_sets_the_anchor(win):
    """끌기는 그대로여야 한다 — 드롭다운이 앵커를 지운다고 끌기가 막히면 안 된다."""
    ax = win.session.fig.axes[0]
    x, y = center(win, ax.get_legend())
    drag(win.canvas, x, y, x - 60, y - 40)
    over = win.session.spec.of("ax0.legend")
    assert over.get("bbox_to_anchor") is not None
    assert over.get("loc") is not None


def test_clearing_the_anchor_is_part_of_the_same_undo_step(win):
    """따로 쌓이면 실행 취소가 loc만 되돌리고 앵커는 지운 채로 둔다."""
    ax = win.session.fig.axes[0]
    x, y = center(win, ax.get_legend())
    drag(win.canvas, x, y, x - 60, y - 40)
    anchor = list(win.session.spec.of("ax0.legend")["bbox_to_anchor"])

    win.select("ax0.legend")
    steps = len(win.session.history)
    win.inspector.edited.emit("loc", "lower right")
    assert len(win.session.history) - steps == 1

    win.undo()
    assert win.session.spec.of("ax0.legend").get("bbox_to_anchor") == anchor


def test_other_legend_props_leave_the_anchor_alone(win):
    """글자 크기를 바꿨다고 위치가 튀면 안 된다."""
    ax = win.session.fig.axes[0]
    x, y = center(win, ax.get_legend())
    drag(win.canvas, x, y, x - 60, y - 40)
    anchor = list(win.session.spec.of("ax0.legend")["bbox_to_anchor"])

    win.select("ax0.legend")
    win.inspector.edited.emit("fontsize", 8.0)
    assert win.session.spec.of("ax0.legend").get("bbox_to_anchor") == anchor


def test_a_dead_pad_field_is_greyed_out(win):
    """값을 넣어도 아무 일이 없는 칸은 그렇다고 말해야 한다."""
    cur = win.session.values("ax0.xlabel")["position"]
    win.session.set_prop("ax0.xlabel", "position", [cur[0] + 0.05, cur[1]])
    win.select("ax0")
    _prop, w = win.inspector._rows["xlabelpad"]
    assert not w.isEnabled()
    assert "효과가 없습니다" in w.toolTip()


def test_live_fields_stay_enabled(win):
    win.select("ax0")
    for name in ("xlabelpad", "ylabelpad", "titlepad", "xlim"):
        _prop, w = win.inspector._rows[name]
        assert w.isEnabled(), name


# --- 실행 취소 뒤에도 캔버스가 종이에 맞는다 ------------------------------------
#
# 끌기는 종이를 다시 맞추므로 figure 크기가 바뀐다. 되돌리면 크기도 돌아오는데
# 캔버스 위젯은 고정 크기라 함께 맞추지 않으면 그대로 남는다. 그러면 새 그림이
# 옛 크기의 위젯에 그려져 잔상이 겹치고, 여러 번 되돌릴수록 심해진다.

def _canvas_matches_paper(win):
    fig = win.session.fig
    w_in, h_in = fig.get_size_inches()
    return (abs(int(w_in * fig.dpi) - win.canvas.width()) <= 1
            and abs(int(h_in * fig.dpi) - win.canvas.height()) <= 1)


def _resize_axes(win, by=220):
    fig = win.session.fig
    win.select("ax1")
    bb = fig.axes[1].get_window_extent()
    x, y = bb.x1, (bb.y0 + bb.y1) / 2
    drag(win.canvas, x, y, x + by, y)


def test_the_canvas_follows_the_paper_after_undo(win):
    _resize_axes(win)
    assert win.session.history.can_undo()
    win.undo()
    assert _canvas_matches_paper(win), (
        f"figure={win.session.fig.get_size_inches()} "
        f"위젯=({win.canvas.width()}, {win.canvas.height()})")


def test_the_canvas_follows_the_paper_after_redo(win):
    _resize_axes(win)
    win.undo()
    win.redo()
    assert _canvas_matches_paper(win)


def test_many_undos_in_a_row_stay_matched(win):
    """여러 번 연속으로 되돌리면 잔상이 겹쳐 보이던 상황."""
    for by in (120, -80, 150):
        _resize_axes(win, by)
    for _ in range(4):
        win.undo()
        assert _canvas_matches_paper(win)
