"""끌기 → 프로퍼티 값.

Origin에서 제목이나 범례를 잡아 끄는 조작에 대응한다. 계산은 전부 Figure
기하라 Qt와 무관하고, 그래서 GUI 없이 테스트된다. UI가 하는 일은 좌표를
넘기고 돌려받은 값을 session.set_prop에 넣는 것뿐이다.

끌기는 '보이는 것을 그대로 옮긴다'가 되어야 한다. 잡은 지점이 어긋나면
집는 순간 그림이 튀고, 그러면 조작이 아니라 사고가 된다. 그래서 시작
시점의 값과 커서를 함께 기억하고 그 차이만 더한다.

figtune이 추가한 텍스트(usertext)는 spec의 texts에 별도로 살지만 끌기는
여기를 함께 거친다. 한때 UI가 따로 옮겼는데, 그 경로에는 잡은 지점 보정도
실행 취소도 종이 맞추기도 없었다. 저장 위치가 다르다고 조작까지 달라질
이유는 없다 — 갈라지는 지점은 session.set_prop 한 곳으로 충분하다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import props as P
from . import selector as sel

# 축 상자가 이보다 작아지면 눈금과 라벨이 겹쳐 아무것도 읽을 수 없다.
MIN_SIZE = 0.05

# 범례의 loc이 상자의 어느 점을 가리키는가. bbox_to_anchor는 그 점을 옮긴다.
LOC_CORNER = {
    "upper right": (1.0, 1.0), "upper left": (0.0, 1.0),
    "lower left": (0.0, 0.0), "lower right": (1.0, 0.0),
    "center left": (0.0, 0.5), "center right": (1.0, 0.5),
    "upper center": (0.5, 1.0), "lower center": (0.5, 0.0),
    "center": (0.5, 0.5),
}


@dataclass(frozen=True)
class Change:
    """set_prop 한 건."""

    path: str
    prop: str
    value: object


@dataclass
class Drag:
    kind: str                       # text | legend | resize
    path: str
    start: tuple                    # 시작 커서 (display 좌표)
    origin: list                    # 시작 시점의 값
    axes: int | None = None
    handle: str | None = None
    loc: str | None = None          # 범례를 끌 때 확정한 loc
    moved: bool = False


def _usertext_transform(fig, path: str):
    """usertext가 자기 위치를 표현하는 좌표계. 못 찾으면 None.

    usertext만 좌표계를 스스로 고른다 (data / axes / figure). 축 좌표로
    가정하면 data 좌표 텍스트가 커서와 다른 속도로 달아난다.
    """
    try:
        art = sel.resolve(fig, path)
    except sel.SelectorError:
        return None
    return getattr(art, "get_transform", lambda: None)()


def _transform(fig, path: str, axes: int | None):
    """이 대상의 위치가 어느 좌표계로 표현되는가."""
    if sel.parse(path).kind == "usertext":
        tr = _usertext_transform(fig, path)
        if tr is not None:
            return tr
    if path.startswith("fig") or axes is None:
        return fig.transFigure
    return fig.axes[axes].transAxes


def _delta(tr, start, x, y) -> tuple[float, float]:
    inv = tr.inverted()
    x0, y0 = inv.transform(start)
    x1, y1 = inv.transform((x, y))
    return float(x1 - x0), float(y1 - y0)


# --- 시작 -----------------------------------------------------------------

def begin(fig, target, x: float, y: float) -> tuple[Drag | None, list[Change]]:
    """끌기를 시작한다. 함께 돌려주는 Change는 시작 시점에 확정해야 하는 값."""
    if target is None:
        return None, []
    if target.kind == "resize":
        return _begin_resize(fig, target, x, y), []
    if target.kind == "layer" and target.movable:
        return _begin_layer(fig, target, x, y), []
    if target.kind == "legend":
        return _begin_legend(fig, target, x, y)
    if target.kind == "text":
        return _begin_text(fig, target, x, y), []
    return None, []


def _begin_resize(fig, target, x, y) -> Drag | None:
    if target.axes is None or target.handle is None:
        return None
    bounds = [float(v) for v in fig.axes[target.axes].get_position().bounds]
    return Drag("resize", target.path, (x, y), bounds,
                axes=target.axes, handle=target.handle)


def _begin_layer(fig, target, x, y) -> Drag | None:
    """축 본체를 잡는다 — 크기는 그대로 두고 자리만 옮긴다."""
    if target.axes is None:
        return None
    bounds = [float(v) for v in fig.axes[target.axes].get_position().bounds]
    return Drag("layer", target.path, (x, y), bounds, axes=target.axes)


def _begin_text(fig, target, x, y) -> Drag | None:
    origin = P.get(fig, target.path, "position")
    if origin is None:
        return None
    return Drag("text", target.path, (x, y),
                [float(v) for v in origin], axes=target.axes)


def _begin_legend(fig, target, x, y) -> tuple[Drag | None, list[Change]]:
    path = target.path
    leg = (fig.legends[0] if path == "fig.legend"
           else fig.axes[target.axes].get_legend())
    if leg is None:
        return None, []

    pins: list[Change] = []
    loc = P.get(fig, path, "loc")
    if loc not in LOC_CORNER:
        # 'best'는 matplotlib이 알아서 두는 자리다. 끌기와 모순되므로 고정한다.
        # 지금 보이는 자리에서 고정하니 집는 순간 튀지는 않는다.
        loc = "upper left"
        pins.append(Change(path, "loc", loc))

    try:
        bb = leg.get_window_extent(fig.canvas.get_renderer())
    except Exception:
        return None, []
    fx, fy = LOC_CORNER[loc]
    corner = (bb.x0 + fx * bb.width, bb.y0 + fy * bb.height)
    tr = _transform(fig, path, target.axes)
    anchor = [float(v) for v in tr.inverted().transform(corner)]
    return Drag("legend", path, (x, y), anchor, axes=target.axes,
                loc=loc), pins


# --- 진행 -----------------------------------------------------------------

def update(fig, d: Drag, x: float, y: float) -> Change | None:
    """커서가 움직였다. 새 값 하나를 돌려준다."""
    if d is None:
        return None
    d.moved = True
    if d.kind == "resize":
        return _update_resize(fig, d, x, y)
    if d.kind == "layer":
        return _update_layer(fig, d, x, y)
    tr = _transform(fig, d.path, d.axes)
    dx, dy = _delta(tr, d.start, x, y)
    prop = "bbox_to_anchor" if d.kind == "legend" else "position"
    return Change(d.path, prop,
                  [round(d.origin[0] + dx, 4), round(d.origin[1] + dy, 4)])


def _update_layer(fig, d: Drag, x, y) -> Change | None:
    """축 상자를 통째로 옮긴다.

    축 상자는 figure 좌표다. transAxes로 재면 상자 자신의 크기를 단위로
    삼게 되어 커서와 다른 거리를 간다. resize와 같은 방식으로 display를
    figure 비율로 직접 환산한다.
    """
    dx = float(x - d.start[0]) / float(fig.bbox.width)
    dy = float(y - d.start[1]) / float(fig.bbox.height)
    x0, y0, w, h = d.origin
    # 폭·높이는 손대지 않는다. 함께 변하면 이동과 크기 조절이 구별되지 않는다.
    return Change(d.path, "position",
                  [round(x0 + dx, 4), round(y0 + dy, 4),
                   round(w, 4), round(h, 4)])


def _update_resize(fig, d: Drag, x, y) -> Change | None:
    # fig.bbox는 numpy 스칼라를 준다. 여기서 걷어내지 않으면 계산 결과가
    # np.float64로 물들어 상태줄과 로그에 그대로 새어 나온다.
    dx = float(x - d.start[0]) / float(fig.bbox.width)
    dy = float(y - d.start[1]) / float(fig.bbox.height)
    x0, y0, w, h = d.origin
    h_ = d.handle or ""

    if "l" in h_:
        # 왼쪽 변은 오른쪽 변을 넘어설 수 없다. 넘게 두면 폭이 음수가 되고
        # matplotlib이 상자를 뒤집어 그린다.
        dx = min(dx, w - MIN_SIZE)
        x0, w = x0 + dx, w - dx
    elif "r" in h_:
        w = max(w + dx, MIN_SIZE)
    if "b" in h_:
        dy = min(dy, h - MIN_SIZE)
        y0, h = y0 + dy, h - dy
    elif "t" in h_:
        h = max(h + dy, MIN_SIZE)

    return Change(d.path, "position",
                  [round(x0, 4), round(y0, 4), round(w, 4), round(h, 4)])
