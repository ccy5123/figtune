"""끌어서 옮기고 크기를 바꾸는 계산.

지켜야 할 것은 하나다 — **집는 순간 튀지 않는다.** 잡은 지점과 대상의 관계가
그대로 유지되어야 조작이지, 어긋나면 사고다. 그래서 시작 커서와 시작 값을
함께 기억하고 그 차이만 더한다. 커서를 움직이지 않았으면 값도 그대로여야 한다.
"""

from pathlib import Path

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


# --- 축 본체를 끌어 옮긴다 ---------------------------------------------------

def test_layer_is_draggable(fig):
    """축은 크기만 바꿀 수 있고 옮길 수는 없었다.

    도형을 잡아 끌면 옮겨지는 것이 캔버스의 기본 기대다. 크기만 되고
    이동이 안 되면 사용자는 '왜 이것만 안 되지'를 매번 겪는다.
    """
    t = hit.Target(kind="layer", path="ax0", label="ax0", axes=0, movable=True)
    d, _ = drag.begin(fig, t, 100, 100)
    assert d is not None and d.kind == "layer"


def test_layer_does_not_jump_on_grab(fig):
    ax = fig.axes[0]
    before = [round(float(v), 4) for v in ax.get_position().bounds]
    t = hit.Target(kind="layer", path="ax0", label="ax0", axes=0, movable=True)
    d, _ = drag.begin(fig, t, 100, 100)
    assert drag.update(fig, d, 100, 100).value == before


def test_layer_move_keeps_its_size(fig):
    """이동은 크기를 바꾸지 않는다. 폭이 함께 변하면 크기 조절과 구별되지 않는다."""
    ax = fig.axes[0]
    _x0, _y0, w, h = (round(float(v), 4) for v in ax.get_position().bounds)
    t = hit.Target(kind="layer", path="ax0", label="ax0", axes=0, movable=True)
    d, _ = drag.begin(fig, t, 100, 100)
    ch = drag.update(fig, d, 160, 130)
    assert ch.value[2] == w and ch.value[3] == h
    assert ch.value[0] > _x0 and ch.value[1] > _y0


def test_layer_move_is_in_figure_coordinates(fig):
    """축 상자는 figure 좌표다. 축 좌표로 재면 커서와 다른 거리를 간다."""
    t = hit.Target(kind="layer", path="ax0", label="ax0", axes=0, movable=True)
    d, _ = drag.begin(fig, t, 100, 100)
    ch = drag.update(fig, d, 100 + float(fig.bbox.width) / 10, 100)
    assert ch.value[0] == pytest.approx(d.origin[0] + 0.1, abs=1e-3)


def test_page_is_still_not_draggable(fig):
    """종이 자체는 끌 대상이 아니다 — 크기는 인스펙터에서 정한다."""
    t = hit.Target(kind="page", path="fig", label="fig")
    assert drag.begin(fig, t, 0, 0)[0] is None


# --- 범례를 놓은 자리에 정확히 둔다 ---------------------------------------------
#
# bbox_to_anchor를 주어도 matplotlib은 borderaxespad(기본 0.5 글꼴 단위,
# 약 7px)를 추가로 밀어 넣는다. 그래서 '지금 자리'를 그대로 앵커로 지정해도
# 그만큼 어긋난다 — 끌면 커서보다 덜 가고, 놓을 때마다 조금씩 밀린다.

def _corner(ax, fig):
    leg = ax.get_legend()
    bb = leg.get_window_extent(fig.canvas.get_renderer())
    a = ax.get_window_extent()
    return ((bb.x0 - a.x0) / a.width, (bb.y1 - a.y0) / a.height)


def test_anchoring_where_it_already_is_does_not_move_it(fig):
    """제자리를 앵커로 지정했으면 제자리에 있어야 한다."""
    from figtune.core import props as P

    ax = fig.axes[0]
    before = _corner(ax, fig)
    P.apply_legend(ax, {"loc": "upper left", "bbox_to_anchor": list(before)})
    fig.canvas.draw()
    now = _corner(ax, fig)

    a = ax.get_window_extent()
    assert abs(now[0] - before[0]) * a.width < 0.5
    assert abs(now[1] - before[1]) * a.height < 0.5


def test_the_legend_moves_exactly_as_far_as_the_cursor(tmp_path):
    """덜 가면 끌 때마다 조금씩 어긋나고, 여러 번 끌면 눈에 띈다.

    실제 앱 경로(Session)로 확인한다. P.apply로 prop을 하나씩 넣으면 범례가
    매번 새로 만들어져 직전 설정이 사라진다 — apply_legend의 docstring이
    경고하는 그것이다.
    """
    import shutil

    from figtune.core.session import Session

    script = tmp_path / "p.py"
    shutil.copy(Path(__file__).resolve().parent.parent
                / "examples" / "panel_uptake.py", script)
    s = Session()
    s.open(script)
    f = s.fig
    ax = f.axes[0]

    leg = ax.get_legend()
    x, y = center(leg, f)
    # 앵커는 끌기 시작 시점의 자리를 기준으로 계산된다. 그러니 기준도
    # 그때의 자리여야 한다 — 'best'를 고정하는 pin이 범례를 한 번 옮긴다.
    bb0 = leg.get_window_extent(f.canvas.get_renderer())
    d, pins = drag.begin(f, hit.Target(kind="legend", path="ax0.legend",
                                       label="legend", axes=0), x, y)
    for pin in pins:
        s.set_prop(pin.path, pin.prop, pin.value)

    ch = drag.update(f, d, x - 80, y - 40)
    s.set_prop(ch.path, ch.prop, ch.value)
    f.canvas.draw()
    bb1 = ax.get_legend().get_window_extent(f.canvas.get_renderer())

    assert abs((bb1.x0 - bb0.x0) - (-80)) < 1.0, bb1.x0 - bb0.x0
    assert abs((bb1.y0 - bb0.y0) - (-40)) < 1.0, bb1.y0 - bb0.y0


# --- 읽은 자리를 그대로 다시 쓰면 제자리 --------------------------------------
#
# 축 라벨의 position은 set_label_coords가 받는 '앵커점'이다. 읽을 때 bbox
# 중심을 돌려주면 정렬(va=top 등)만큼 어긋나고, 끌기는 그만큼 덜 간다.
# artist 자신의 transform이 앵커를 알고 있으므로 bbox도 정렬도 회전도
# 볼 필요가 없다.

@pytest.mark.parametrize("path", ["ax0.title", "ax0.xlabel", "ax0.ylabel"])
def test_reading_and_writing_a_position_does_not_move_it(fig, path):
    from figtune.core import props as P

    art = {"ax0.title": fig.axes[0].title,
           "ax0.xlabel": fig.axes[0].xaxis.label,
           "ax0.ylabel": fig.axes[0].yaxis.label}[path]
    r = fig.canvas.get_renderer()
    before = art.get_window_extent(r)

    P.apply(fig, path, "position", P.get(fig, path, "position"))
    fig.canvas.draw()
    now = art.get_window_extent(r)
    assert abs(now.x0 - before.x0) < 0.5, now.x0 - before.x0
    assert abs(now.y0 - before.y0) < 0.5, now.y0 - before.y0


@pytest.mark.parametrize("path,dx,dy", [
    ("ax0.title", 60, 30),
    ("ax0.xlabel", 40, 25),
    ("ax0.ylabel", 35, 20),
    ("ax0.xlabel", -22, -13),
])
def test_a_text_moves_exactly_as_far_as_the_cursor(fig, path, dx, dy):
    """덜 가면 끌 때마다 어긋나고, 여러 번 끌면 눈에 띈다."""
    from figtune.core import props as P

    art = {"ax0.title": fig.axes[0].title,
           "ax0.xlabel": fig.axes[0].xaxis.label,
           "ax0.ylabel": fig.axes[0].yaxis.label}[path]
    r = fig.canvas.get_renderer()
    before = art.get_window_extent(r)
    x, y = center(art, fig)

    d, _ = drag.begin(fig, hit.Target(kind="text", path=path, label=path,
                                      axes=0, movable=True), x, y)
    ch = drag.update(fig, d, x + dx, y + dy)
    P.apply(fig, ch.path, ch.prop, ch.value)
    fig.canvas.draw()

    now = art.get_window_extent(r)
    assert abs((now.x0 - before.x0) - dx) < 1.0, now.x0 - before.x0
    assert abs((now.y0 - before.y0) - dy) < 1.0, now.y0 - before.y0


def test_repeated_drags_do_not_accumulate_error(fig):
    """한 번에 1px씩 틀리면 열 번 끌었을 때 10px이 된다."""
    from figtune.core import props as P

    art = fig.axes[0].xaxis.label
    r = fig.canvas.get_renderer()
    before = art.get_window_extent(r)
    target = hit.Target(kind="text", path="ax0.xlabel", label="x",
                        axes=0, movable=True)

    for _ in range(5):
        x, y = center(art, fig)
        d, _ = drag.begin(fig, target, x, y)
        ch = drag.update(fig, d, x + 10, y + 6)
        P.apply(fig, ch.path, ch.prop, ch.value)
        fig.canvas.draw()

    now = art.get_window_extent(r)
    assert abs((now.x0 - before.x0) - 50) < 1.0, now.x0 - before.x0
    assert abs((now.y0 - before.y0) - 30) < 1.0, now.y0 - before.y0
