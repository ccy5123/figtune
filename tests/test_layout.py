"""종이를 내용에 맞춘다.

규칙은 하나다 — **종이 = 모든 구성요소의 경계 + 여백.** 네 방향이 같게
동작하고, 늘기도 줄기도 한다.

여기서 틀리기 쉬운 것이 둘 있다.
  · 경계를 축 상자로 재면 안 된다. 제목과 축 라벨은 상자 **밖**에 그려지므로
    상자가 [0,1] 안이어도 글자는 종이를 넘어가 잘린다.
  · 계산은 인치로 해야 한다. figure 좌표(0~1)로 하면 종이 크기가 바뀌는
    순간 같은 0.5가 다른 물리 위치를 뜻해, 건드리지 않은 패널이 따라 움직인다.
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from figtune.core import layout


def inches_box(fig, i):
    """i번 축 상자를 인치로. 종이 크기가 바뀌어도 비교할 수 있다."""
    w, h = fig.get_size_inches()
    x0, y0, bw, bh = fig.axes[i].get_position().bounds
    return [round(x0 * w, 4), round(y0 * h, 4),
            round(bw * w, 4), round(bh * h, 4)]


def content_box(fig):
    bb = fig.get_tightbbox(fig.canvas.get_renderer())
    return [round(v, 4) for v in (bb.x0, bb.y0, bb.x1, bb.y1)]


def apply(fig, growth):
    if growth is None:
        return
    fig.set_size_inches(*growth.size_inches)
    for path, box in growth.positions.items():
        fig.axes[int(path[2:])].set_position(box)


def settle(fig, passes=4):
    """수렴할 때까지 맞춘다. 크기가 바뀌면 matplotlib이 배치를 다시 잡는다."""
    for _ in range(passes):
        g = layout.fit_to_content(fig)
        if g is None:
            return
        apply(fig, g)
        fig.canvas.draw()


@pytest.fixture
def fig():
    f, ax = plt.subplots(figsize=(6, 4))
    ax.plot([0, 1], [0, 1])
    ax.set_title("T")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    f.canvas.draw()
    yield f
    plt.close(f)


# --- 아무것도 할 게 없을 때 --------------------------------------------------

def test_no_axes_means_nothing_to_do():
    f = plt.figure()
    assert layout.fit_to_content(f) is None
    plt.close(f)


def test_settled_figure_reports_no_change(fig):
    settle(fig)
    assert layout.fit_to_content(fig) is None


def test_tiny_difference_is_ignored(fig):
    """부동소수점 오차로 종이가 계속 자라면 끌 때마다 캔버스가 떨린다."""
    settle(fig)
    x0, y0, w, h = fig.axes[0].get_position().bounds
    fig.axes[0].set_position([x0, y0, w + 1e-9, h])
    assert layout.fit_to_content(fig) is None


# --- 규칙: 내용 경계 + 여백 --------------------------------------------------

def test_paper_hugs_the_content_with_a_margin(fig):
    fig.axes[0].set_position([0.2, 0.2, 0.5, 0.5])
    fig.canvas.draw()
    settle(fig)

    w, h = fig.get_size_inches()
    x0, y0, x1, y1 = content_box(fig)
    m = layout.MARGIN
    assert x0 == pytest.approx(m, abs=1e-2)
    assert y0 == pytest.approx(m, abs=1e-2)
    assert w - x1 == pytest.approx(m, abs=1e-2)
    assert h - y1 == pytest.approx(m, abs=1e-2)


def test_all_four_sides_behave_the_same(fig):
    """좌우가 상하와 다르게 동작하면 예측할 수 없다."""
    fig.axes[0].set_position([0.35, 0.35, 0.3, 0.3])
    fig.canvas.draw()
    settle(fig)

    w, h = fig.get_size_inches()
    x0, y0, x1, y1 = content_box(fig)
    assert x0 == pytest.approx(w - x1, abs=1e-2)
    assert y0 == pytest.approx(h - y1, abs=1e-2)


def test_nothing_is_clipped(fig):
    fig.axes[0].set_position([0.15, 0.02, 0.8, 0.96])
    fig.canvas.draw()
    settle(fig)

    w, h = fig.get_size_inches()
    x0, y0, x1, y1 = content_box(fig)
    assert x0 >= -1e-3 and y0 >= -1e-3
    assert x1 <= w + 1e-3 and y1 <= h + 1e-3


def test_fit_is_idempotent(fig):
    fig.axes[0].set_position([0.15, 0.02, 0.8, 0.96])
    fig.canvas.draw()
    settle(fig)
    assert layout.fit_to_content(fig) is None


# --- 늘기도 줄기도 한다 ------------------------------------------------------

def test_taller_content_grows_the_paper(fig):
    settle(fig)
    before = fig.get_size_inches()[1]
    x0, y0, w, h = fig.axes[0].get_position().bounds
    fig.axes[0].set_position([x0, y0, w, h * 1.3])       # 제목을 위로 민다
    fig.canvas.draw()
    settle(fig)
    assert fig.get_size_inches()[1] > before


def test_shorter_content_shrinks_the_paper(fig):
    """보고된 증상: 제목이 처음보다 낮아졌는데 흰 영역이 그대로였다."""
    settle(fig)
    before = fig.get_size_inches()[1]
    x0, y0, w, h = fig.axes[0].get_position().bounds
    fig.axes[0].set_position([x0, y0, w, h * 0.6])
    fig.canvas.draw()
    settle(fig)
    assert fig.get_size_inches()[1] < before


def test_narrower_content_shrinks_the_paper(fig):
    """좌우도 상하와 똑같이 줄어야 한다."""
    settle(fig)
    before = fig.get_size_inches()[0]
    x0, y0, w, h = fig.axes[0].get_position().bounds
    fig.axes[0].set_position([x0, y0, w * 0.6, h])
    fig.canvas.draw()
    settle(fig)
    assert fig.get_size_inches()[0] < before


def test_content_pushed_outside_is_brought_back_in(fig):
    """왼쪽·아래로 나간 것도 종이 안으로 들어와야 한다."""
    fig.axes[0].set_position([-0.2, -0.1, 0.7, 0.8])
    fig.canvas.draw()
    settle(fig)
    x0, y0, _x1, _y1 = content_box(fig)
    assert x0 >= -1e-3 and y0 >= -1e-3


# --- 그림 자체는 건드리지 않는다 ----------------------------------------------

def test_axes_keeps_its_physical_size(fig):
    """종이만 바뀌어야 한다. 그림이 함께 커지면 글자 크기가 어긋나 보인다."""
    fig.axes[0].set_position([0.2, 0.2, 0.5, 0.5])
    fig.canvas.draw()
    before = inches_box(fig, 0)[2:]
    apply(fig, layout.fit_to_content(fig))
    assert inches_box(fig, 0)[2:] == pytest.approx(before, abs=1e-3)


def test_panels_keep_their_spacing():
    """건드리지 않은 패널이 따라 움직이면 그림이 통째로 어긋난다."""
    f, axes = plt.subplots(1, 2, figsize=(8, 3))
    x0, y0, w, h = axes[0].get_position().bounds
    axes[0].set_position([x0 - 0.25, y0, w, h])       # 한쪽만 끌어낸다
    f.canvas.draw()
    # 맞추기 **직전**을 기준으로 삼는다. 끌어낸 것 자체가 간격을 바꾸는 것은
    # 당연하고, 여기서 보려는 것은 맞추기가 간격을 건드리는가다.
    gap_before = (inches_box(f, 1)[0]
                  - (inches_box(f, 0)[0] + inches_box(f, 0)[2]))
    size_before = inches_box(f, 1)[2:]
    apply(f, layout.fit_to_content(f))

    gap_after = (inches_box(f, 1)[0]
                 - (inches_box(f, 0)[0] + inches_box(f, 0)[2]))
    assert gap_after == pytest.approx(gap_before, abs=1e-3)
    assert inches_box(f, 1)[2:] == pytest.approx(size_before, abs=1e-3)
    plt.close(f)


# --- 무엇을 경계로 보는가 ----------------------------------------------------

def test_title_and_labels_count_as_content(fig):
    """축 상자만 보면 상자가 [0,1] 안이어도 글자는 밖으로 나가 잘린다."""
    fig.axes[0].set_position([0.15, 0.02, 0.8, 0.96])
    fig.canvas.draw()
    x0, y0, w, h = fig.axes[0].get_position().bounds
    assert 0 <= x0 and 0 <= y0 and x0 + w <= 1 and y0 + h <= 1

    g = layout.fit_to_content(fig)
    assert g is not None and g.size_inches[1] > 4.0


def test_suptitle_counts_as_content():
    f, ax = plt.subplots(figsize=(6, 4))
    ax.set_position([0.1, 0.1, 0.8, 0.95])
    f.suptitle("Very tall suptitle", y=1.06)
    f.canvas.draw()
    assert layout.fit_to_content(f) is not None
    plt.close(f)


def test_falls_back_to_boxes_without_a_renderer(monkeypatch):
    """렌더러를 못 얻어도 죽지 않고 상자 기준으로라도 판단해야 한다."""
    f, ax = plt.subplots(figsize=(6, 4))
    ax.set_position([0.1, 0.1, 1.2, 0.8])
    monkeypatch.setattr(layout, "_tight_extent", lambda *a, **k: None)
    g = layout.fit_to_content(f)
    assert g is not None and g.size_inches[0] > 6.0
    plt.close(f)


# --- set_prop에 그대로 넣을 수 있는 형태 --------------------------------------

def test_changes_lists_figure_size_first():
    """축 위치는 새 종이 크기를 전제로 계산된 값이다. 순서가 뒤집히면
    중간 상태에서 축이 엉뚱한 자리에 놓인다."""
    f, axes = plt.subplots(1, 2, figsize=(8, 3))
    axes[1].set_position([0.6, 0.1, 0.6, 0.8])
    f.canvas.draw()
    changes = layout.fit_to_content(f).changes()
    assert changes[0][:2] == ("fig", "size_inches")
    assert {c[0] for c in changes[1:]} == {"ax0", "ax1"}
    assert all(c[1] == "position" and len(c[2]) == 4 for c in changes[1:])
    plt.close(f)


def test_values_are_plain_floats(fig):
    """matplotlib은 np.float64를 준다. 그대로 두면 상태줄과 로그에 샌다."""
    fig.axes[0].set_position([0.1, 0.1, 1.1, 0.8])
    fig.canvas.draw()
    g = layout.fit_to_content(fig)
    assert all(type(v) is float for v in g.size_inches)
    for box in g.positions.values():
        assert all(type(v) is float for v in box), [type(v) for v in box]
