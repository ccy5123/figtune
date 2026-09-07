"""조립 격자 — 칸을 묶고 나누고 채우는 규칙.

화면에 어떻게 그리는지는 UI가 정한다. 여기서는 Qt를 쓰지 않는다 — 그래야
화면 없이 확인할 수 있고, 나중에 다른 프론트엔드가 같은 규칙을 쓴다.

지켜야 할 것 셋:
  · 칸은 늘 격자를 빈틈없이 덮는다. 구멍이 생기면 GridSpec으로 그릴 수 없다.
  · 순서는 읽는 순서다 — (a)(b)(c) 라벨이 그 순서로 붙는다.
  · 조용히 잃지 않는다. 채워진 칸 둘을 묶으라고 하면 거부한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..i18n import t as _t


class LayoutError(ValueError):
    """할 수 없는 조작."""


@dataclass
class Slot:
    """격자에서 한 자리를 차지하는 칸. ref가 그 자리에 놓일 그림이다."""

    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    ref: str | None = None

    def cells(self):
        for r in range(self.row, self.row + self.rowspan):
            for c in range(self.col, self.col + self.colspan):
                yield r, c

    def inside(self, row, col, rowspan, colspan) -> bool:
        return (row <= self.row and self.row + self.rowspan <= row + rowspan
                and col <= self.col and self.col + self.colspan <= col + colspan)

    def touches(self, row, col, rowspan, colspan) -> bool:
        return any(row <= r < row + rowspan and col <= c < col + colspan
                   for r, c in self.cells())


class GridLayout:
    """rows x cols 격자. 처음에는 칸마다 자리 하나씩."""

    def __init__(self, rows: int, cols: int):
        self.rows = int(rows)
        self.cols = int(cols)
        self.slots: list[Slot] = [Slot(r, c)
                                  for r in range(self.rows)
                                  for c in range(self.cols)]

    # --- 조회 -------------------------------------------------------------

    def _sort(self) -> None:
        """읽는 순서로 되돌린다. 라벨이 그 순서로 붙는다."""
        self.slots.sort(key=lambda s: (s.row, s.col))

    def index_at(self, row: int, col: int) -> int:
        for i, s in enumerate(self.slots):
            if (row, col) in set(s.cells()):
                return i
        raise LayoutError(_t("({r},{c})는 격자를 벗어납니다.", r=row, c=col))

    def slot_at(self, row: int, col: int) -> Slot:
        return self.slots[self.index_at(row, col)]

    def empty_slots(self) -> list[Slot]:
        return [s for s in self.slots if not s.ref]

    def is_complete(self) -> bool:
        return bool(self.slots) and not self.empty_slots()

    # --- 묶기 · 나누기 -----------------------------------------------------

    def merge(self, row: int, col: int, rowspan: int, colspan: int) -> None:
        """직사각형 범위를 한 칸으로 묶는다."""
        if rowspan <= 1 and colspan <= 1:
            return
        if (row < 0 or col < 0 or row + rowspan > self.rows
                or col + colspan > self.cols):
            raise LayoutError(_t(
                "묶을 범위가 격자를 벗어납니다: ({r},{c}) {rs}x{cs}",
                r=row, c=col, rs=rowspan, cs=colspan))

        touched = [s for s in self.slots if s.touches(row, col, rowspan, colspan)]
        partial = [s for s in touched if not s.inside(row, col, rowspan, colspan)]
        if partial:
            raise LayoutError(_t(
                "이미 묶인 칸에 걸쳐 있습니다. 그 칸을 먼저 나누세요."))

        filled = [s for s in touched if s.ref]
        if len(filled) > 1:
            raise LayoutError(_t(
                "채워진 칸이 {n}개입니다. 하나만 남기고 비운 뒤 묶으세요.",
                n=len(filled)))

        for s in touched:
            self.slots.remove(s)
        self.slots.append(Slot(row, col, rowspan, colspan,
                               ref=filled[0].ref if filled else None))
        self._sort()

    def split(self, index: int) -> None:
        """묶인 칸을 원래 칸들로 되돌린다. 내용은 첫 칸에 남는다."""
        s = self.slots[index]
        if s.rowspan <= 1 and s.colspan <= 1:
            return
        self.slots.remove(s)
        for r, c in s.cells():
            self.slots.append(Slot(r, c, ref=s.ref if (r, c) == (s.row, s.col)
                                   else None))
        self._sort()

    # --- 채우기 -----------------------------------------------------------

    def assign(self, index: int, ref: str) -> None:
        """칸에 그림을 놓는다.

        같은 그림을 두 칸에 놓지 못하게 한다. 두 칸에 있으면 어느 쪽을
        고쳐야 할지 알 수 없고, 병합 결과에도 같은 그림이 두 번 나온다.
        """
        for i, s in enumerate(self.slots):
            if i != index and s.ref == ref:
                raise LayoutError(_t(
                    "{ref}는 이미 다른 칸에 있습니다.", ref=ref))
        self.slots[index].ref = ref

    def clear(self, index: int) -> None:
        self.slots[index].ref = None

    # --- 병합 스펙으로 ------------------------------------------------------

    def to_panels(self) -> list:
        """montage_build.PanelRef 목록. 빈 칸이 있으면 거부한다."""
        from .montage_build import PanelRef

        empty = self.empty_slots()
        if empty:
            raise LayoutError(_t(
                "빈 칸이 {n}개 남았습니다. 모두 채운 뒤 만드세요.",
                n=len(empty)))
        return [PanelRef(script=s.ref, row=s.row, col=s.col,
                         rowspan=s.rowspan, colspan=s.colspan)
                for s in self.slots]
