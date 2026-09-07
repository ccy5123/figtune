"""끌 때 다른 요소에 붙는다.

논문 그림에서 눈으로 맞춘 정렬은 1~2픽셀씩 어긋난다. 인쇄하면 보이고,
보이면 다시 만져야 한다. 붙기는 그 왕복을 없앤다.

계산은 화면 좌표(픽셀)에서 한다. 대상마다 속성의 단위가 다르기 때문이다 —
축은 figure 비율, 텍스트는 축 좌표, 범례는 앵커. 화면에서 맞추고 그 보정을
**커서 위치**에 얹으면, 단위와 무관하게 같은 규칙이 걸리고 끌기 계산은
손댈 것이 없다.

Qt도 matplotlib도 쓰지 않는다 — 순수한 기하다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# 이보다 멀면 붙지 않는다. 크게 잡으면 원하는 자리에 두려는데 자꾸 끌려가고,
# 작게 잡으면 맞추려 해도 안 붙는다.
THRESHOLD = 6.0


@dataclass(frozen=True)
class Guide:
    """무엇에 붙었는지 보여주는 선.

    보이지 않으면 사용자는 왜 튀었는지 알 수 없다.
    """

    axis: str          # "x" | "y"
    at: float          # 그 축에서의 화면 좌표
    lo: float          # 선을 그릴 범위 (반대 축)
    hi: float


@dataclass(frozen=True)
class Snap:
    dx: float = 0.0
    dy: float = 0.0
    guides: list = field(default_factory=list)


def _ok(box) -> bool:
    return (box is not None and len(box) == 4
            and all(isinstance(v, (int, float)) and math.isfinite(v)
                    for v in box))


def _lines(box, axis: str) -> tuple[float, float, float]:
    """그 축에서 맞춰볼 세 자리: 시작 · 가운데 · 끝."""
    lo, hi = (box[0], box[2]) if axis == "x" else (box[1], box[3])
    return lo, (lo + hi) / 2.0, hi


def _best(box, candidates, axis: str, threshold: float):
    """가장 가까운 정렬. (보정값, 붙은 좌표, 상대 상자) 또는 None."""
    best = None
    for cand in candidates:
        for mine in _lines(box, axis):
            for theirs in _lines(cand, axis):
                gap = theirs - mine
                if abs(gap) > threshold:
                    continue
                if best is None or abs(gap) < abs(best[0]):
                    best = (gap, theirs, cand)
    return best


def _guide(box, cand, axis: str, at: float) -> Guide:
    """붙은 자리를 가로지르는 선. 두 상자를 다 덮어야 눈으로 이어진다."""
    i, j = (1, 3) if axis == "x" else (0, 2)
    lo = min(box[i], cand[i])
    hi = max(box[j], cand[j])
    return Guide(axis=axis, at=at, lo=lo, hi=hi)


def snap(box, candidates, threshold: float = THRESHOLD) -> Snap:
    """움직이는 상자를 가까운 정렬에 붙인다.

    box는 지금 커서 위치에서의 (x0, y0, x1, y1)이고, 돌려주는 dx·dy는
    커서에 더할 화면 픽셀 보정이다.

    두 축은 따로 본다 — x는 붙고 y는 안 붙는 경우가 흔하다.

    threshold가 0이면 아무것도 하지 않는다. 수식키를 누른 채 끌면 원하는
    자리에 정확히 둘 수 있어야 한다.
    """
    if threshold <= 0 or not _ok(box):
        return Snap()

    good = [c for c in candidates if _ok(c)]
    dx = dy = 0.0
    guides = []
    for axis in ("x", "y"):
        found = _best(box, good, axis, threshold)
        if found is None:
            continue
        gap, at, cand = found
        if axis == "x":
            dx = gap
        else:
            dy = gap
        guides.append(_guide(box, cand, axis, at))
    return Snap(dx=dx, dy=dy, guides=guides)
