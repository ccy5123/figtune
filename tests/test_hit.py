"""클릭 → 대상 판정.

직접 조작에서 이 판정이 전부다. 틀리면 사용자가 누른 것과 편집되는 것이
달라지고, 그건 조용히 그림을 망가뜨린다.

특히 지켜야 할 것:
  · 축 하나를 누르면 눈금·축선·격자·범위가 함께 열린다 (Origin의 Axis Dialog)
  · 위에 그려진 것이 먼저 잡힌다 (범례 > 데이터 > 축 > 레이어 > 페이지)
  · 크기 조절 핸들은 고른 뒤에만 생긴다 — 늘 있으면 축선 클릭을 가로챈다
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from figtune.core import hit, introspect
from figtune.core import selector as sel


@pytest.fixture
def fig():
    f, ax = plt.subplots(figsize=(6, 4))
    ax.plot([0, 1, 2], [0, 1, 0], label="a")
    ax.set_title("Title")
    ax.set_xlabel("X label")
    ax.set_ylabel("Y label")
    ax.legend(loc="upper right")
    f.canvas.draw()
    yield f
    plt.close(f)


def kinds(targets):
    return [t.kind for t in targets]


def first(targets, kind):
    return next((t for t in targets if t.kind == kind), None)


# --- 대상 판정 --------------------------------------------------------------

def test_plot_area_hits_the_layer(fig):
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    # 데이터가 없는 빈 구석
    ts = hit.hit(fig, None, bb.x0 + 20, bb.y0 + 10)
    assert first(ts, "layer").path == "ax0"


def test_outside_the_page_hits_the_page(fig):
    ts = hit.hit(fig, None, 2, 2)
    assert kinds(ts) == ["page"]
    assert ts[0].path == "fig"


def test_title_is_editable_and_movable(fig):
    ax = fig.axes[0]
    bb = ax.title.get_window_extent(fig.canvas.get_renderer())
    t = first(hit.hit(fig, None, (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2), "text")
    assert t.path == "ax0.title"
    assert t.movable and t.editable
    assert t.cursor == hit.MOVE


@pytest.mark.parametrize("which,path", [("xlabel", "ax0.xlabel"),
                                        ("ylabel", "ax0.ylabel")])
def test_axis_labels_are_hit(fig, which, path):
    ax = fig.axes[0]
    art = ax.xaxis.label if which == "xlabel" else ax.yaxis.label
    bb = art.get_window_extent(fig.canvas.get_renderer())
    t = first(hit.hit(fig, None, (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2), "text")
    assert t.path == path


def test_legend_is_movable_and_wins_over_the_layer(fig):
    ax = fig.axes[0]
    bb = ax.get_legend().get_window_extent(fig.canvas.get_renderer())
    ts = hit.hit(fig, None, (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2)
    assert kinds(ts).index("legend") < kinds(ts).index("layer")
    assert first(ts, "legend").movable


# --- 축: 한 대상이 여러 selector를 묶는다 -------------------------------------

def test_clicking_tick_labels_opens_the_whole_axis(fig):
    """Origin의 Axis Dialog — 눈금·축선·격자·범위가 한 대상이다."""
    ax = fig.axes[0]
    r = fig.canvas.get_renderer()
    lbl = next(t for t in ax.get_xticklabels() if t.get_text())
    bb = lbl.get_window_extent(r)
    t = first(hit.hit(fig, None, (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2), "axis")
    assert t is not None and t.axis == "x"
    assert set(t.scope()) == {"ax0.xtick.major", "ax0.xtick.minor",
                              "ax0.spine:bottom", "ax0.grid.x", "ax0"}


def test_clicking_the_spine_opens_the_axis(fig):
    ax = fig.axes[0]
    bb = ax.spines["left"].get_window_extent()
    t = first(hit.hit(fig, None, bb.x0, (bb.y0 + bb.y1) / 2), "axis")
    assert t is not None and t.axis == "y"
    assert "ax0.spine:left" in t.scope()


def test_axis_scope_selectors_all_parse(fig):
    """묶인 selector가 하나라도 깨지면 대화상자가 열리다 만다."""
    ax = fig.axes[0]
    bb = ax.spines["bottom"].get_window_extent()
    t = first(hit.hit(fig, None, (bb.x0 + bb.x1) / 2, bb.y0), "axis")
    for path in t.scope():
        sel.parse(path)                       # 예외가 나면 실패


# --- 크기 조절 핸들 ---------------------------------------------------------

def test_no_handles_until_the_layer_is_selected(fig):
    """핸들이 늘 있으면 축선을 누를 수 없다."""
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    assert first(hit.hit(fig, None, bb.x1, bb.y1), "resize") is None


@pytest.mark.parametrize("corner,handle,cursor", [
    ("x0y0", "bl", hit.SIZE_BDIAG),
    ("x1y1", "tr", hit.SIZE_BDIAG),
    ("x0y1", "tl", hit.SIZE_FDIAG),
    ("x1y0", "br", hit.SIZE_FDIAG),
])
def test_selected_layer_exposes_corner_handles(fig, corner, handle, cursor):
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    x = bb.x0 if corner.startswith("x0") else bb.x1
    y = bb.y0 if corner.endswith("y0") else bb.y1
    t = first(hit.hit(fig, None, x, y, selected="ax0"), "resize")
    assert t is not None and t.handle == handle and t.cursor == cursor


def test_edge_handles_give_directional_cursors(fig):
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    mid_y, mid_x = (bb.y0 + bb.y1) / 2, (bb.x0 + bb.x1) / 2
    left = first(hit.hit(fig, None, bb.x0, mid_y, selected="ax0"), "resize")
    bottom = first(hit.hit(fig, None, mid_x, bb.y0, selected="ax0"), "resize")
    assert (left.handle, left.cursor) == ("l", hit.SIZE_H)
    assert (bottom.handle, bottom.cursor) == ("b", hit.SIZE_V)


def test_handle_is_the_topmost_target(fig):
    """핸들을 잡았으면 그 아래의 축·레이어가 가로채면 안 된다."""
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    ts = hit.hit(fig, None, bb.x0, bb.y0, selected="ax0")
    assert ts[0].kind == "resize"


def test_handles_only_for_the_selected_axes():
    f, axes = plt.subplots(1, 2)
    f.canvas.draw()
    bb = axes[1].get_window_extent()
    ts = hit.hit(f, None, bb.x0, bb.y0, selected="ax0")
    assert first(ts, "resize") is None          # ax1 모서리인데 ax0을 골랐다
    plt.close(f)


# --- 데이터 artist ----------------------------------------------------------

def test_data_artist_is_hit_through_the_tree(fig):
    ax = fig.axes[0]
    tree = introspect.build(fig)
    xd, yd = ax.transData.transform((1.0, 1.0))
    ts = hit.hit(fig, tree, xd, yd)
    assert first(ts, "plot").path == "ax0.line0"


def test_data_artist_beats_the_layer(fig):
    ax = fig.axes[0]
    tree = introspect.build(fig)
    xd, yd = ax.transData.transform((1.0, 1.0))
    k = kinds(hit.hit(fig, tree, xd, yd))
    assert k.index("plot") < k.index("layer")


def test_no_tree_means_no_data_hits(fig):
    """hover는 tree 없이 부른다 — 무거운 contains()를 피하려는 것이다."""
    ax = fig.axes[0]
    xd, yd = ax.transData.transform((1.0, 1.0))
    assert first(hit.hit(fig, None, xd, yd), "plot") is None


# --- 커서 ------------------------------------------------------------------

def test_cursor_over_text_is_move(fig):
    bb = fig.axes[0].title.get_window_extent(fig.canvas.get_renderer())
    assert hit.cursor_at(fig, (bb.x0 + bb.x1) / 2,
                         (bb.y0 + bb.y1) / 2) == hit.MOVE


def test_cursor_over_empty_layer_is_move(fig):
    """축 본체는 잡아 옮길 수 있다 — 커서가 그렇다고 말해야 한다.

    한때 화살표였다. 끌어도 아무 일이 없었으니 정직한 커서였지만, 이동을
    붙인 뒤로는 할 수 있는 일을 숨기는 것이 된다.
    """
    bb = fig.axes[0].get_window_extent()
    assert hit.cursor_at(fig, bb.x0 + 20, bb.y0 + 10) == hit.MOVE


def test_cursor_on_selected_corner_is_diagonal(fig):
    bb = fig.axes[0].get_window_extent()
    assert hit.cursor_at(fig, bb.x1, bb.y1, selected="ax0") == hit.SIZE_BDIAG


# --- 빈 요소는 잡히지 않는다 -------------------------------------------------

def test_empty_title_is_not_hit():
    """제목이 없으면 그 자리는 페이지다. 빈 bbox를 잡으면 유령 대상이 생긴다."""
    f, ax = plt.subplots()
    f.canvas.draw()
    bb = ax.get_window_extent()
    ts = hit.hit(f, None, (bb.x0 + bb.x1) / 2, bb.y1 + 20)
    assert first(ts, "text") is None
    plt.close(f)


def test_suptitle_is_hit():
    f, ax = plt.subplots()
    f.suptitle("Sup")
    f.canvas.draw()
    bb = f._suptitle.get_window_extent(f.canvas.get_renderer())
    t = first(hit.hit(f, None, (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2), "text")
    assert t is not None and t.path == "fig.suptitle" and t.editable
    plt.close(f)


def test_figure_legend_is_hit():
    f, ax = plt.subplots()
    (ln,) = ax.plot([0, 1], [0, 1], label="a")
    f.legend(handles=[ln], loc="upper right")
    f.canvas.draw()
    bb = f.legends[0].get_window_extent(f.canvas.get_renderer())
    t = first(hit.hit(f, None, (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2), "legend")
    assert t is not None and t.path == "fig.legend" and t.movable
    plt.close(f)


# --- 다패널 ----------------------------------------------------------------

def test_each_panel_reports_its_own_index():
    f, axes = plt.subplots(1, 2)
    f.canvas.draw()
    for i, ax in enumerate(axes):
        bb = ax.get_window_extent()
        t = first(hit.hit(f, None, bb.x0 + 15, bb.y0 + 10), "layer")
        assert t.path == f"ax{i}" and t.axes == i
    plt.close(f)


# --- 판정 지도 (캐시) -------------------------------------------------------

def test_map_lookup_matches_the_one_shot_call(fig):
    """편의 함수와 지도 조회가 갈라지면 GUI만 다르게 동작하게 된다."""
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    m = hit.build(fig)
    for x, y in [(bb.x0 + 20, bb.y0 + 10), (bb.x0, bb.y0 + 30), (2, 2)]:
        assert [t.path for t in m.at(x, y)] == \
            [t.path for t in hit.hit(fig, None, x, y)]


def test_map_is_a_snapshot_not_a_live_query(fig):
    """캐시가 아니면 hover마다 12ms가 든다 — 그 사실을 여기서 못박는다.

    지도를 만든 뒤 제목을 옮겨도 지도는 예전 자리를 가리켜야 한다. 살아있는
    질의로 바뀌면 이 테스트가 먼저 깨진다.
    """
    ax = fig.axes[0]
    r = fig.canvas.get_renderer()
    before = ax.title.get_window_extent(r)
    m = hit.build(fig, r)
    cx, cy = (before.x0 + before.x1) / 2, (before.y0 + before.y1) / 2
    assert first(m.at(cx, cy), "text") is not None

    ax.title.set_position((0.05, 1.3))
    fig.canvas.draw()
    assert first(m.at(cx, cy), "text") is not None, "지도가 살아있는 질의가 됐다"
    assert first(hit.build(fig).at(cx, cy), "text") is None, "새 지도는 따라와야 한다"


def test_hover_lookup_ignores_data_artists(fig):
    """artist.contains()는 점 수에 비례해 무겁다. hover는 건너뛰어야 한다."""
    ax = fig.axes[0]
    xd, yd = ax.transData.transform((1.0, 1.0))
    m = hit.build(fig)
    assert first(m.at(xd, yd), "plot") is None
    assert first(m.at(xd, yd, artists=hit.artist_hits(fig, introspect.build(fig),
                                                     xd, yd)), "plot") is not None


def test_artist_hits_are_grouped_by_axes():
    f, axes = plt.subplots(1, 2)
    for ax in axes:
        ax.plot([0, 1], [0, 1])
    f.canvas.draw()
    tree = introspect.build(f)
    xd, yd = axes[1].transData.transform((0.5, 0.5))
    got = hit.artist_hits(f, tree, xd, yd)
    assert set(got) == {1} and got[1][0].path == "ax1.line0"
    plt.close(f)


def test_map_exposes_axes_box_for_dragging(fig):
    m = hit.build(fig)
    bb = fig.axes[0].get_window_extent()
    assert [round(v) for v in m.axes_box(0)] == [round(v) for v in
                                                 (bb.x0, bb.y0, bb.x1, bb.y1)]
    assert m.axes_box(9) is None


def test_page_is_always_the_last_resort(fig):
    """어디를 눌러도 대상이 하나는 나와야 한다. 빈손이면 UI가 멈춘다."""
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    for x, y in [(1, 1), (bb.x0 + 5, bb.y0 + 5), (bb.x1 - 5, bb.y1 - 5)]:
        ts = hit.hit(fig, None, x, y)
        assert ts and ts[-1].kind == "page"
