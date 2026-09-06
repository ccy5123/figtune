"""끌어서 옮기고 크기를 바꾸는 계산.

지켜야 할 것은 하나다 — **집는 순간 튀지 않는다.** 잡은 지점과 대상의 관계가
그대로 유지되어야 조작이지, 어긋나면 사고다. 그래서 시작 커서와 시작 값을
함께 기억하고 그 차이만 더한다. 커서를 움직이지 않았으면 값도 그대로여야 한다.
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from figtune.core import drag, hit


@pytest.fixture
def fig():
    f, ax = plt.subplots(figsize=(6, 4))
    ax.plot([0, 1], [0, 1], label="a")
    ax.set_title("T")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.legend(loc="upper right")
    f.canvas.draw()
    yield f
    plt.close(f)


def _with_usertext(coords):
    """figtune이 추가한 텍스트가 하나 있는 figure. spec 없이 artist만 만든다."""
    f, ax = plt.subplots(figsize=(6, 4))
    ax.plot([0, 1], [0, 1])
    pos = (0.5, 0.5) if coords == "axes" else (0.5, 0.5)
    art = ax.text(pos[0], pos[1], "note",
                  transform=ax.transAxes if coords == "axes" else ax.transData)
    art._figtune_id = "t001"
    f.canvas.draw()
    return f, "ax0.text:t001", art


@pytest.fixture
def usertext():
    f, path, art = _with_usertext("axes")
    yield f, path, art
    plt.close(f)


@pytest.fixture
def usertext_data():
    f, path, art = _with_usertext("data")
    yield f, path, art
    plt.close(f)


def target_at(fig, x, y, selected=None, kind=None):
    ts = hit.hit(fig, None, x, y, selected=selected)
    return next(t for t in ts if kind is None or t.kind == kind)


def center(artist, fig):
    bb = artist.get_window_extent(fig.canvas.get_renderer())
    return (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2


# --- 튀지 않는다 -----------------------------------------------------------

def test_grabbing_without_moving_changes_nothing(fig):
    ax = fig.axes[0]
    x, y = center(ax.title, fig)
    t = target_at(fig, x, y, kind="text")
    d, _ = drag.begin(fig, t, x, y)
    ch = drag.update(fig, d, x, y)
    assert ch.value == [round(v, 4) for v in ax.title.get_position()]


def test_legend_does_not_jump_on_grab(fig):
    ax = fig.axes[0]
    x, y = center(ax.get_legend(), fig)
    d, _ = drag.begin(fig, target_at(fig, x, y, kind="legend"), x, y)
    ch = drag.update(fig, d, x, y)
    # 잡기만 했으면 앵커는 시작값 그대로
    assert ch.value == [round(v, 4) for v in d.origin]


def test_resize_without_moving_keeps_the_box(fig):
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    t = target_at(fig, bb.x1, bb.y1, selected="ax0", kind="resize")
    d, _ = drag.begin(fig, t, bb.x1, bb.y1)
    ch = drag.update(fig, d, bb.x1, bb.y1)
    assert ch.value == [round(v, 4) for v in ax.get_position().bounds]


# --- 텍스트 이동 -----------------------------------------------------------

def test_title_follows_the_cursor(fig):
    ax = fig.axes[0]
    x, y = center(ax.title, fig)
    d, _ = drag.begin(fig, target_at(fig, x, y, kind="text"), x, y)
    ch = drag.update(fig, d, x + 60, y + 12)          # 오른쪽 위로

    inv = ax.transAxes.inverted()
    want_dx = inv.transform((x + 60, y))[0] - inv.transform((x, y))[0]
    assert ch.path == "ax0.title" and ch.prop == "position"
    assert ch.value[0] == pytest.approx(d.origin[0] + want_dx, abs=1e-3)
    assert ch.value[1] > d.origin[1]


def test_moved_title_actually_lands_where_dropped(fig):
    """계산이 맞아도 적용 후 자리가 다르면 소용없다."""
    from figtune.core import props as P
    ax = fig.axes[0]
    x, y = center(ax.title, fig)
    d, _ = drag.begin(fig, target_at(fig, x, y, kind="text"), x, y)
    ch = drag.update(fig, d, x + 50, y)
    P.apply(fig, ch.path, ch.prop, ch.value)
    fig.canvas.draw()
    assert center(ax.title, fig)[0] == pytest.approx(x + 50, abs=2.0)


def test_axis_label_is_draggable(fig):
    ax = fig.axes[0]
    x, y = center(ax.xaxis.label, fig)
    d, _ = drag.begin(fig, target_at(fig, x, y, kind="text"), x, y)
    ch = drag.update(fig, d, x, y - 10)
    assert ch.path == "ax0.xlabel" and ch.value[1] < d.origin[1]


def test_suptitle_moves_in_figure_coordinates():
    f, ax = plt.subplots()
    f.suptitle("S")
    f.canvas.draw()
    x, y = center(f._suptitle, f)
    t = next(t for t in hit.hit(f, None, x, y) if t.kind == "text")
    d, _ = drag.begin(f, t, x, y)
    ch = drag.update(f, d, x + f.bbox.width * 0.1, y)
    assert ch.path == "fig.suptitle"
    assert ch.value[0] == pytest.approx(d.origin[0] + 0.1, abs=1e-3)
    plt.close(f)


# --- 범례 ------------------------------------------------------------------

def test_legend_drag_sets_the_anchor(fig):
    ax = fig.axes[0]
    x, y = center(ax.get_legend(), fig)
    d, _ = drag.begin(fig, target_at(fig, x, y, kind="legend"), x, y)
    ch = drag.update(fig, d, x - 40, y - 30)
    assert ch.path == "ax0.legend" and ch.prop == "bbox_to_anchor"
    assert ch.value[0] < d.origin[0] and ch.value[1] < d.origin[1]


def test_best_placement_is_pinned_before_dragging():
    """'best'는 matplotlib이 알아서 두는 자리다. 끌기와 모순되므로 고정한다."""
    f, ax = plt.subplots()
    ax.plot([0, 1], [0, 1], label="a")
    ax.legend(loc="best")
    f.canvas.draw()
    x, y = center(ax.get_legend(), f)
    t = next(t for t in hit.hit(f, None, x, y) if t.kind == "legend")
    d, pins = drag.begin(f, t, x, y)
    assert [(p.prop, p.value) for p in pins] == [("loc", "upper left")]
    assert d.loc == "upper left"
    plt.close(f)


@pytest.mark.parametrize("loc", ["upper right", "lower left", "center",
                                 "upper center"])
def test_legend_loc_reads_back(loc):
    """matplotlib은 loc을 정수로 들고 있다. 되읽지 못하면 인스펙터의 위치
    드롭다운이 늘 비고, 끌기는 엉뚱한 모서리를 앵커로 잡는다."""
    from figtune.core import props as P
    f, ax = plt.subplots()
    ax.plot([0, 1], [0, 1], label="a")
    ax.legend(loc=loc)
    f.canvas.draw()
    assert P.get(f, "ax0.legend", "loc") == loc
    plt.close(f)


def test_legend_loc_is_none_when_given_as_coordinates():
    """좌표로 준 loc은 이름이 없다. 지어내면 드롭다운이 거짓말을 한다."""
    from figtune.core import props as P
    f, ax = plt.subplots()
    ax.plot([0, 1], [0, 1], label="a")
    ax.legend(loc=(0.2, 0.7))
    f.canvas.draw()
    assert P.get(f, "ax0.legend", "loc") is None
    plt.close(f)


def test_figure_legend_loc_reads_back():
    """FacetGrid 범례는 figure에 붙는다 — 같은 구멍이 있었다."""
    from figtune.core import props as P
    f, ax = plt.subplots()
    (ln,) = ax.plot([0, 1], [0, 1], label="a")
    f.legend(handles=[ln], loc="lower right")
    f.canvas.draw()
    assert P.get(f, "fig.legend", "loc") == "lower right"
    plt.close(f)


def test_explicit_loc_is_left_alone(fig):
    ax = fig.axes[0]
    x, y = center(ax.get_legend(), fig)
    d, pins = drag.begin(fig, target_at(fig, x, y, kind="legend"), x, y)
    assert pins == [] and d.loc == "upper right"


def test_anchor_matches_the_loc_corner(fig):
    """loc이 'upper right'면 앵커는 범례 상자의 오른쪽 위다."""
    ax = fig.axes[0]
    leg = ax.get_legend()
    bb = leg.get_window_extent(fig.canvas.get_renderer())
    x, y = center(leg, fig)
    d, _ = drag.begin(fig, target_at(fig, x, y, kind="legend"), x, y)
    want = ax.transAxes.inverted().transform((bb.x1, bb.y1))
    assert d.origin == pytest.approx(list(want), abs=1e-6)


# --- 크기 조절 -------------------------------------------------------------

@pytest.mark.parametrize("handle,idx,sign", [
    ("r", 2, +1),      # 오른쪽 변 → 폭이 는다
    ("t", 3, +1),      # 위쪽 변  → 높이가 는다
])
def test_dragging_an_edge_grows_the_box(fig, handle, idx, sign):
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    pos = {"r": (bb.x1, (bb.y0 + bb.y1) / 2), "t": ((bb.x0 + bb.x1) / 2, bb.y1)}
    x, y = pos[handle]
    d, _ = drag.begin(fig, target_at(fig, x, y, selected="ax0", kind="resize"), x, y)
    ch = drag.update(fig, d, x + (30 if handle == "r" else 0),
                     y + (0 if handle == "r" else 30))
    assert (ch.value[idx] - d.origin[idx]) * sign > 0


def test_dragging_the_left_edge_moves_and_shrinks(fig):
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    x, y = bb.x0, (bb.y0 + bb.y1) / 2
    d, _ = drag.begin(fig, target_at(fig, x, y, selected="ax0", kind="resize"), x, y)
    ch = drag.update(fig, d, x + 40, y)
    assert ch.value[0] > d.origin[0]        # 왼쪽 모서리가 오른쪽으로
    assert ch.value[2] < d.origin[2]        # 폭은 줄어든다
    # 오른쪽 변은 제자리
    assert ch.value[0] + ch.value[2] == pytest.approx(d.origin[0] + d.origin[2],
                                                      abs=1e-3)


def test_box_never_collapses(fig):
    """폭이 음수가 되면 matplotlib이 상자를 뒤집어 그린다."""
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    x, y = bb.x0, (bb.y0 + bb.y1) / 2
    d, _ = drag.begin(fig, target_at(fig, x, y, selected="ax0", kind="resize"), x, y)
    ch = drag.update(fig, d, bb.x1 + 500, y)          # 오른쪽 변을 한참 넘어서
    assert ch.value[2] >= drag.MIN_SIZE
    assert ch.value[0] + ch.value[2] == pytest.approx(d.origin[0] + d.origin[2],
                                                      abs=1e-3)


def test_corner_changes_both_dimensions(fig):
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    d, _ = drag.begin(fig, target_at(fig, bb.x1, bb.y1, selected="ax0",
                                     kind="resize"), bb.x1, bb.y1)
    ch = drag.update(fig, d, bb.x1 + 30, bb.y1 + 20)
    assert ch.value[2] > d.origin[2] and ch.value[3] > d.origin[3]


def test_resize_applies_cleanly(fig):
    from figtune.core import props as P
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    d, _ = drag.begin(fig, target_at(fig, bb.x1, bb.y1, selected="ax0",
                                     kind="resize"), bb.x1, bb.y1)
    ch = drag.update(fig, d, bb.x1 + 30, bb.y1 + 20)
    P.apply(fig, ch.path, ch.prop, ch.value)
    assert [round(v, 4) for v in ax.get_position().bounds] == ch.value


# --- 다루지 않는 것 ---------------------------------------------------------

def test_plain_plot_targets_are_not_draggable(fig):
    t = hit.Target(kind="plot", path="ax0.line0", label="line0", axes=0)
    assert drag.begin(fig, t, 0, 0) == (None, [])


def test_layer_and_page_are_not_draggable(fig):
    for kind, path in (("layer", "ax0"), ("page", "fig")):
        t = hit.Target(kind=kind, path=path, label=path, axes=0)
        assert drag.begin(fig, t, 0, 0)[0] is None


def test_usertext_does_not_jump_on_grab(usertext):
    """usertext도 다른 텍스트와 같은 규칙을 따른다.

    한때 usertext만 이 모듈을 우회해 커서 좌표를 위치로 그대로 썼다. 잡은
    지점과의 차이를 기억하지 않아, 글자 끝을 잡으면 앵커가 커서 밑으로
    순간이동했다 — 이 파일이 막으려는 바로 그 현상이다.
    """
    f, path, art = usertext
    x, y = center(art, f)
    t = hit.Target(kind="text", path=path, label="t", axes=0, movable=True)
    d, _ = drag.begin(f, t, x, y)
    ch = drag.update(f, d, x, y)
    assert ch.value == [round(v, 4) for v in art.get_position()]


def test_usertext_moves_by_the_cursor_delta(usertext):
    f, path, art = usertext
    x, y = center(art, f)
    t = hit.Target(kind="text", path=path, label="t", axes=0, movable=True)
    d, _ = drag.begin(f, t, x, y)
    before = [round(v, 4) for v in art.get_position()]
    ch = drag.update(f, d, x + 40, y)
    assert ch.value[0] > before[0] and ch.value[1] == before[1]


def test_data_coordinate_usertext_uses_its_own_transform(usertext_data):
    """usertext는 좌표계를 스스로 고른다(data/axes/figure).

    축 좌표로 가정하면 data 좌표 텍스트가 커서보다 몇 배 빠르게 달아난다.
    """
    f, path, art = usertext_data
    ax = f.axes[0]
    x, y = center(art, f)
    t = hit.Target(kind="text", path=path, label="t", axes=0, movable=True)
    d, _ = drag.begin(f, t, x, y)
    ch = drag.update(f, d, x + 40, y)

    # 커서가 실제로 지나간 data 거리와 같아야 한다
    inv = ax.transData.inverted()
    expect = inv.transform((x + 40, y))[0] - inv.transform((x, y))[0]
    assert ch.value[0] == pytest.approx(art.get_position()[0] + expect, abs=1e-3)


def test_values_are_plain_python_floats(fig):
    """matplotlib은 np.float64를 돌려준다. 그대로 두면 상태줄과 로그에
    np.float64(...)로 새어 나오고, spec 경계까지 딸려 간다."""
    ax = fig.axes[0]
    bb = ax.get_window_extent()
    d, _ = drag.begin(fig, target_at(fig, bb.x1, bb.y1, selected="ax0",
                                     kind="resize"), bb.x1, bb.y1)
    ch = drag.update(fig, d, bb.x1 + 20, bb.y1 + 20)
    assert all(type(v) is float for v in ch.value), [type(v) for v in ch.value]
    assert all(type(v) is float for v in d.origin)

    x, y = center(ax.title, fig)
    d2, _ = drag.begin(fig, target_at(fig, x, y, kind="text"), x, y)
    ch2 = drag.update(fig, d2, x + 10, y)
    assert all(type(v) is float for v in ch2.value)
