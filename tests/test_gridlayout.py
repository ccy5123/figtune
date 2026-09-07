"""조립 격자 모델.

칸을 묶고 나누고 채우는 규칙만 담는다. 화면에 어떻게 그리는지는 UI가
정하고, 여기서는 Qt를 쓰지 않는다 — 그래야 화면 없이 확인할 수 있다.

지켜야 할 것:
  · 칸은 늘 격자를 빈틈없이 덮는다 (구멍이 생기면 그릴 수 없다)
  · 순서는 읽는 순서다 — (a)(b)(c) 라벨이 그 순서로 붙는다
  · 조용히 잃지 않는다: 채워진 칸 둘을 묶으라고 하면 거부한다
"""

import pytest

from figtune.core.gridlayout import GridLayout, LayoutError


@pytest.fixture
def g():
    return GridLayout(2, 3)


def _cells(layout):
    return [(s.row, s.col, s.rowspan, s.colspan) for s in layout.slots]


# --- 시작 -------------------------------------------------------------------

def test_starts_as_one_slot_per_cell(g):
    assert len(g.slots) == 6
    assert _cells(g)[:3] == [(0, 0, 1, 1), (0, 1, 1, 1), (0, 2, 1, 1)]


def test_every_cell_is_covered(g):
    covered = {(r, c) for s in g.slots
               for r in range(s.row, s.row + s.rowspan)
               for c in range(s.col, s.col + s.colspan)}
    assert covered == {(r, c) for r in range(2) for c in range(3)}


# --- 묶기 -------------------------------------------------------------------

def test_merging_a_region_makes_one_slot(g):
    g.merge(0, 0, 1, 2)                   # 첫 행의 왼쪽 두 칸
    assert (0, 0, 1, 2) in _cells(g)
    assert len(g.slots) == 5


def test_merging_keeps_reading_order(g):
    """라벨이 (a)(b)(c) 순으로 붙으려면 순서가 읽는 순서여야 한다."""
    g.merge(1, 0, 1, 3)
    assert _cells(g) == [(0, 0, 1, 1), (0, 1, 1, 1), (0, 2, 1, 1),
                         (1, 0, 1, 3)]


def test_merging_carries_the_one_filled_cell(g):
    g.assign(g.index_at(0, 1), "b.py")
    g.merge(0, 0, 1, 2)
    assert g.slot_at(0, 0).ref == "b.py"


def test_merging_two_filled_cells_is_refused(g):
    """한쪽을 조용히 버리면 사용자는 무엇이 사라졌는지 모른다."""
    g.assign(g.index_at(0, 0), "a.py")
    g.assign(g.index_at(0, 1), "b.py")
    with pytest.raises(LayoutError, match="비운"):
        g.merge(0, 0, 1, 2)


def test_merging_across_a_partial_slot_is_refused(g):
    """이미 묶인 칸을 반만 걸치면 격자에 구멍이 생긴다."""
    g.merge(0, 1, 1, 2)
    with pytest.raises(LayoutError, match="걸쳐"):
        g.merge(0, 0, 1, 2)


def test_merging_outside_the_grid_is_refused(g):
    with pytest.raises(LayoutError, match="벗어"):
        g.merge(0, 2, 1, 2)


def test_merging_a_single_cell_does_nothing(g):
    before = _cells(g)
    g.merge(0, 0, 1, 1)
    assert _cells(g) == before


# --- 나누기 -----------------------------------------------------------------

def test_splitting_restores_the_cells(g):
    g.merge(0, 0, 2, 2)
    g.split(g.index_at(0, 0))
    assert len(g.slots) == 6
    assert _cells(g)[0] == (0, 0, 1, 1)


def test_splitting_keeps_the_content_in_the_first_cell(g):
    g.merge(0, 0, 1, 2)
    g.assign(g.index_at(0, 0), "a.py")
    g.split(g.index_at(0, 0))
    assert g.slot_at(0, 0).ref == "a.py"
    assert g.slot_at(0, 1).ref is None


def test_splitting_a_plain_cell_does_nothing(g):
    before = _cells(g)
    g.split(g.index_at(0, 0))
    assert _cells(g) == before


# --- 채우기 -----------------------------------------------------------------

def test_assign_and_clear(g):
    i = g.index_at(1, 2)
    g.assign(i, "z.py")
    assert g.slot_at(1, 2).ref == "z.py"
    g.clear(i)
    assert g.slot_at(1, 2).ref is None


def test_the_same_document_is_not_placed_twice(g):
    """같은 그림이 두 칸에 있으면 어느 쪽을 고쳐야 할지 알 수 없다."""
    g.assign(g.index_at(0, 0), "a.py")
    with pytest.raises(LayoutError, match="이미"):
        g.assign(g.index_at(0, 1), "a.py")


def test_reassigning_the_same_cell_is_fine(g):
    i = g.index_at(0, 0)
    g.assign(i, "a.py")
    g.assign(i, "a.py")
    assert g.slot_at(0, 0).ref == "a.py"


# --- 완성 여부 ---------------------------------------------------------------

def test_incomplete_until_every_slot_is_filled(g):
    assert not g.is_complete()
    for i, _s in enumerate(g.slots):
        g.assign(i, f"f{i}.py")
    assert g.is_complete()


def test_empty_slots_are_reported_for_the_message(g):
    g.assign(g.index_at(0, 0), "a.py")
    assert len(g.empty_slots()) == 5


# --- 병합 스펙으로 ------------------------------------------------------------

def test_panels_come_out_in_reading_order(g):
    g.merge(0, 0, 1, 3)
    g.assign(g.index_at(0, 0), "wide.py")
    for r, c in ((1, 0), (1, 1), (1, 2)):
        g.assign(g.index_at(r, c), f"p{c}.py")

    panels = g.to_panels()
    assert [p.script for p in panels] == ["wide.py", "p0.py", "p1.py", "p2.py"]
    assert (panels[0].row, panels[0].col, panels[0].colspan) == (0, 0, 3)


def test_to_panels_refuses_an_unfinished_layout(g):
    with pytest.raises(LayoutError, match="빈 칸"):
        g.to_panels()


def test_the_result_survives_montage_validation(g):
    """placements()가 겹침과 범위 이탈을 다시 본다 — 여기서 통과해야 한다."""
    from figtune.core.montage_build import MontageSpec

    g.merge(0, 0, 2, 1)
    for i, _s in enumerate(g.slots):
        g.assign(i, f"f{i}.py")
    ms = MontageSpec(rows=g.rows, cols=g.cols, panels=g.to_panels())
    assert len(ms.placements()) == len(g.slots)
