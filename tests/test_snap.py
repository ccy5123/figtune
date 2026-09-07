"""끌 때 다른 요소에 붙는다.

논문 그림에서 눈으로 맞춘 정렬은 1~2픽셀씩 어긋난다. 인쇄하면 보이고,
보이면 다시 만져야 한다. 붙기는 그 왕복을 없앤다.

계산은 화면 좌표(픽셀)에서 한다. 대상마다 속성의 단위가 다르기 때문이다 —
축은 figure 비율, 텍스트는 축 좌표, 범례는 앵커. 화면에서 맞추고 그 보정을
커서 위치에 얹으면, 단위와 무관하게 같은 규칙이 걸린다.

Qt도 matplotlib도 쓰지 않는다 — 순수한 기하다.
"""

import pytest

from figtune.core.snap import Guide, snap

# 움직이는 상자: 왼쪽 100, 오른쪽 200, 위 100, 아래 200 (가운데 150, 150)
BOX = (100.0, 100.0, 200.0, 200.0)


def _dx(*a, **kw):
    return snap(*a, **kw).dx


def _dy(*a, **kw):
    return snap(*a, **kw).dy


# --- 붙는다 ------------------------------------------------------------------

def test_nothing_nearby_does_not_move_it(BOX=BOX):
    r = snap(BOX, [(500.0, 500.0, 600.0, 600.0)])
    assert (r.dx, r.dy) == (0.0, 0.0)
    assert r.guides == []


def test_left_edges_snap():
    """왼쪽 모서리끼리 3px 어긋났으면 붙인다."""
    assert _dx(BOX, [(103.0, 400.0, 180.0, 500.0)]) == 3.0


def test_right_edges_snap():
    assert _dx(BOX, [(300.0, 400.0, 204.0, 500.0)]) == 4.0


def test_centres_snap():
    """가운데 정렬은 눈으로 맞추기 가장 어렵다."""
    assert _dx(BOX, [(102.0, 400.0, 202.0, 500.0)]) == 2.0


def test_vertical_works_the_same_way():
    # 후보를 5px 위로 통째로 옮긴 것 — 세 자리가 모두 -5로 일치한다.
    # (한 자리만 맞추면 후보의 가운데가 내 모서리에 더 가까울 수 있어,
    #  무엇에 붙었는지가 값에서 드러나지 않는다.)
    assert _dy(BOX, [(400.0, 95.0, 500.0, 195.0)]) == -5.0


def test_far_away_does_not_pull():
    assert _dx(BOX, [(120.0, 400.0, 220.0, 500.0)]) == 0.0


def test_the_nearest_alignment_wins():
    """여러 개가 임계값 안에 있으면 가장 가까운 것으로 간다."""
    assert _dx(BOX, [(105.0, 0.0, 205.0, 10.0),
                     (101.0, 0.0, 201.0, 10.0)]) == 1.0


def test_the_two_axes_are_independent():
    """x는 붙고 y는 안 붙는 경우가 흔하다."""
    r = snap(BOX, [(102.0, 400.0, 202.0, 500.0)])
    assert r.dx == 2.0 and r.dy == 0.0


def test_threshold_is_configurable():
    assert _dx(BOX, [(108.0, 0.0, 208.0, 10.0)]) == 0.0
    assert _dx(BOX, [(108.0, 0.0, 208.0, 10.0)], threshold=10.0) == 8.0


def test_snapping_can_be_turned_off():
    """수식키를 누르면 원하는 자리에 정확히 둘 수 있어야 한다."""
    r = snap(BOX, [(102.0, 400.0, 202.0, 500.0)], threshold=0.0)
    assert (r.dx, r.dy) == (0.0, 0.0)


# --- 안내선 ------------------------------------------------------------------

def test_a_guide_marks_what_it_snapped_to():
    """무엇에 붙었는지 보이지 않으면 왜 튀었는지 알 수 없다."""
    r = snap(BOX, [(103.0, 400.0, 180.0, 500.0)])
    assert len(r.guides) == 1
    g = r.guides[0]
    assert isinstance(g, Guide)
    assert g.axis == "x" and g.at == 103.0


def test_the_guide_spans_both_boxes():
    """안내선이 짧으면 무엇과 맞춘 것인지 눈으로 잇지 못한다."""
    g = snap(BOX, [(103.0, 400.0, 180.0, 500.0)]).guides[0]
    assert g.lo <= 100.0 and g.hi >= 500.0


def test_two_guides_when_both_axes_snap():
    r = snap(BOX, [(103.0, 103.0, 203.0, 203.0)])
    assert {g.axis for g in r.guides} == {"x", "y"}


def test_no_guides_when_nothing_snaps():
    assert snap(BOX, []).guides == []


# --- 경계 --------------------------------------------------------------------

def test_a_degenerate_candidate_is_ignored():
    """폭이 0인 상자는 아무것도 알려주지 않는다."""
    assert _dx(BOX, [(103.0, 400.0, 103.0, 400.0)]) == 3.0


@pytest.mark.parametrize("bad", [None, (1.0, 2.0), (float("nan"),) * 4])
def test_broken_candidates_are_skipped(bad):
    """하나가 깨졌다고 끌기가 멈추면 안 된다."""
    r = snap(BOX, [bad, (103.0, 400.0, 180.0, 500.0)])
    assert r.dx == 3.0
