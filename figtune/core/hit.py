"""클릭 좌표 → 편집 대상.

Origin의 조작 모델을 그대로 옮긴다. 어디를 눌렀는지가 곧 무엇을 편집할지다.
트리에서 대상을 찾아 오른쪽 폼으로 눈을 옮기는 대신, 그림에서 직접 집는다.

핵심은 **한 대상이 여러 selector를 묶는다**는 것이다. 축을 누르면 눈금·축선·
격자·범위가 함께 열려야 한다. 이들은 selector 트리에서는 서로 다른 가지지만
사용자에게는 '이 축'이라는 하나의 대상이다. Origin의 Axis Dialog가 정확히
이 구조다.

Qt를 import하지 않는다. 여기서 하는 일은 Figure 기하 계산일 뿐이고, 커서는
이름으로만 돌려준다(UI가 자기 커서로 옮긴다). 그래서 GUI 없이 테스트된다.

좌표계: matplotlib display 좌표(왼쪽 아래가 원점, 물리 픽셀)를 쓴다. Qt 위젯
좌표로의 변환은 어댑터의 몫이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import selector as sel

# 커서 이름. UI가 자기 툴킷 커서로 옮긴다.
ARROW, MOVE, TEXT = "arrow", "move", "text"
SIZE_H, SIZE_V = "size_h", "size_v"
SIZE_BDIAG, SIZE_FDIAG = "size_bdiag", "size_fdiag"

# 모서리 핸들 판정 폭(픽셀). 너무 좁으면 못 잡고 너무 넓으면 안쪽 클릭을
# 가로챈다. 창 가장자리 끌기의 관습을 따른다.
HANDLE_TOL = 5.0
# 축선·눈금라벨 판정에 주는 여유. 축선은 1px라 그대로는 누를 수 없다.
EDGE_TOL = 4.0


@dataclass(frozen=True)
class Target:
    """클릭이 가리키는 편집 대상."""

    kind: str                   # page|layer|axis|plot|text|legend|resize
    path: str                   # 대표 selector (선택 상태로 쓰는 것)
    label: str                  # 사람이 읽을 이름
    selectors: tuple = ()       # 대화상자가 열 범위. 비면 (path,)와 같다
    cursor: str = ARROW
    axes: int | None = None
    axis: str | None = None     # kind=="axis" 일 때 'x' | 'y'
    handle: str | None = None   # kind=="resize" 일 때 l|r|t|b|tl|tr|bl|br
    movable: bool = False       # 끌어서 위치를 바꿀 수 있는가
    editable: bool = False      # 제자리에서 글자를 고칠 수 있는가

    def scope(self) -> tuple:
        return self.selectors or (self.path,)


# selector 종류 -> 끌기 대상 종류. 여기 없는 것은 옮길 수 없다.
# (축은 상자를 옮기고, 텍스트는 좌표를, 범례는 앵커를 옮긴다.)
_DRAG_KIND = {
    "axes": "layer",
    "text": "text", "figtext": "text", "txt": "text", "usertext": "text",
    "legend": "legend", "figlegend": "legend",
}


def target_for_path(fig, path: str) -> Target | None:
    """selector 하나를 끌기 대상으로 바꾼다. 못 옮기는 것이면 None.

    캔버스에서 잡은 것 말고도 함께 고른 것들을 같이 옮기려면, 커서 아래에
    없는 대상까지 Target으로 만들 수 있어야 한다.
    """
    try:
        s = sel.parse(path)
    except sel.SelectorError:
        return None
    kind = _DRAG_KIND.get(s.kind)
    if kind is None:
        return None
    if kind == "layer" and s.axes is not None and s.axes >= len(fig.axes):
        return None
    return Target(kind=kind, path=path, label=path, cursor=MOVE,
                  axes=s.axes, movable=True)


# --- 기하 도우미 -----------------------------------------------------------

def _renderer(fig):
    try:
        return fig.canvas.get_renderer()
    except AttributeError:                       # pragma: no cover - 백엔드 차이
        fig.canvas.draw()
        return fig.canvas.get_renderer()


def _bbox(artist, renderer):
    try:
        bb = artist.get_window_extent(renderer)
    except TypeError:
        bb = artist.get_window_extent()
    except Exception:
        return None
    if bb is None or bb.width < 0 or bb.height < 0:
        return None
    return bb


# --- 크기 조절 핸들 ---------------------------------------------------------

_HANDLE_CURSOR = {"l": SIZE_H, "r": SIZE_H, "t": SIZE_V, "b": SIZE_V,
                  "tl": SIZE_FDIAG, "br": SIZE_FDIAG,
                  "tr": SIZE_BDIAG, "bl": SIZE_BDIAG}


def handle_of(box, x, y, tol: float = HANDLE_TOL) -> str | None:
    """축 상자 모서리 중 어디를 잡았는가. box는 (x0, y0, x1, y1).

    선택된 대상에만 핸들을 내주는 것이 Origin의 방식이다. 늘 내주면 축선을
    누르려는 클릭을 가로채 축 편집으로 못 들어간다.
    """
    if box is None:
        return None
    x0, y0, x1, y1 = box
    if not (x0 - tol <= x <= x1 + tol and y0 - tol <= y <= y1 + tol):
        return None
    vert = "t" if abs(y - y1) <= tol else ("b" if abs(y - y0) <= tol else "")
    horz = "l" if abs(x - x0) <= tol else ("r" if abs(x - x1) <= tol else "")
    return (vert + horz) or None


# --- 축 대상 ---------------------------------------------------------------

def axis_target(ax_i: int, which: str, side: str) -> Target:
    """축 하나를 누르면 눈금·축선·격자·범위가 함께 열린다."""
    base = sel.axes(ax_i)
    return Target(
        kind="axis",
        path=sel.tick(ax_i, which, "major"),
        label=f"{base}.{which}axis",
        selectors=(sel.tick(ax_i, which, "major"),
                   sel.tick(ax_i, which, "minor"),
                   sel.spine(ax_i, side),
                   sel.grid(ax_i, which),
                   base),
        axes=ax_i,
        axis=which,
    )


def _label_side(ax, which: str) -> str:
    """눈금이 어느 쪽에 붙어 있는가. 축선 selector를 고르는 데 쓴다."""
    if which == "x":
        return "top" if ax.xaxis.get_ticks_position() == "top" else "bottom"
    return "right" if ax.yaxis.get_ticks_position() == "right" else "left"


# --- 미리 계산한 판정 지도 ---------------------------------------------------
#
# get_window_extent()는 눈금 라벨마다 글자 배치를 다시 계산해서, 2패널 그림
# 한 번 판정에 12ms가 든다. hover마다 부르면 60fps 예산의 3/4을 커서에 쓴다.
#
# 기하는 다시 그릴 때만 바뀐다. 그래서 그릴 때 한 번 재두고, 그 뒤에는
# 사각형 비교만 한다. 캐시 무효화 시점이 draw 하나뿐이라 어긋날 여지가 없다.


@dataclass(frozen=True)
class Region:
    x0: float
    y0: float
    x1: float
    y1: float
    target: Target
    pad: float = 0.0

    def contains(self, x: float, y: float) -> bool:
        return (self.x0 - self.pad <= x <= self.x1 + self.pad
                and self.y0 - self.pad <= y <= self.y1 + self.pad)


@dataclass(frozen=True)
class _AxesMap:
    index: int
    box: tuple                       # (x0, y0, x1, y1)
    layer: Target
    legend: Region | None = None
    texts: tuple = ()
    axis: tuple = ()


@dataclass(frozen=True)
class HitMap:
    """한 번 그린 뒤의 기하. 다음 draw 전까지 유효하다."""

    axes: tuple = ()
    figure: tuple = ()
    page: Target = field(default_factory=lambda: Target(kind="page", path="fig",
                                                        label="figure"))

    def at(self, x: float, y: float, selected: str | None = None,
           artists: dict | None = None) -> list[Target]:
        """위에 그려진 것부터. artists는 클릭 때만 넘긴다."""
        out: list[Target] = []
        h = self._handle(selected, x, y)
        if h is not None:
            out.append(h)
        for am in self.axes:
            if am.legend is not None and am.legend.contains(x, y):
                out.append(am.legend.target)
            if artists:
                out += artists.get(am.index, [])
            out += [r.target for r in am.texts if r.contains(x, y)]
            out += [r.target for r in am.axis if r.contains(x, y)]
            if _in_box(am.box, x, y):
                out.append(am.layer)
        out += [r.target for r in self.figure if r.contains(x, y)]
        out.append(self.page)
        return out

    def cursor(self, x: float, y: float, selected: str | None = None) -> str:
        """hover용. artist는 보지 않는다 — contains()가 점 수에 비례해 무겁고,
        커서를 바꾸는 대상(텍스트·범례·핸들)은 전부 bbox로 잡힌다."""
        for t in self.at(x, y, selected=selected):
            if t.cursor != ARROW:
                return t.cursor
        return ARROW

    def axes_box(self, ax_i: int) -> tuple | None:
        for am in self.axes:
            if am.index == ax_i:
                return am.box
        return None

    def bbox_of(self, path: str, target: Target | None = None) -> tuple | None:
        """대상이 차지하는 사각형. 고른 것을 표시하는 데 쓴다.

        축 대상은 눈금 라벨과 축선 여러 조각으로 나뉘어 있으므로 합집합을
        돌려준다 — 조각 하나만 테두리를 치면 무엇을 골랐는지 알 수 없다.

        target을 주면 그것과 같은 조각만 모은다. 위·아래 축선은 둘 다 'x축'
        이라 path가 같은데, 합치면 테두리가 상자 세로 전체를 덮어 무엇을
        골랐는지 도로 알 수 없어진다.
        """
        def matches(t):
            return t == target if target is not None else t.path == path

        rects = []
        for am in self.axes:
            if matches(am.layer):
                return am.box
            if am.legend is not None and matches(am.legend.target):
                return (am.legend.x0, am.legend.y0, am.legend.x1, am.legend.y1)
            rects += [(r.x0, r.y0, r.x1, r.y1)
                      for r in am.texts + am.axis if matches(r.target)]
        rects += [(r.x0, r.y0, r.x1, r.y1)
                  for r in self.figure if matches(r.target)]
        if not rects:
            return None
        return (min(r[0] for r in rects), min(r[1] for r in rects),
                max(r[2] for r in rects), max(r[3] for r in rects))

    def _handle(self, selected, x, y) -> Target | None:
        if not selected:
            return None
        try:
            s = sel.parse(selected)
        except sel.SelectorError:
            return None
        if s.kind != "axes" or s.axes is None:
            return None
        box = self.axes_box(s.axes)
        if box is None:
            return None
        h = handle_of(box, x, y)
        if h is None:
            return None
        return Target(kind="resize", path=selected, label=f"{selected} {h}",
                      cursor=_HANDLE_CURSOR[h], axes=s.axes, handle=h)


def _in_box(box, x, y, pad=0.0) -> bool:
    return (box is not None and box[0] - pad <= x <= box[2] + pad
            and box[1] - pad <= y <= box[3] + pad)


def _rect(bb):
    return None if bb is None else (bb.x0, bb.y0, bb.x1, bb.y1)


def build(fig, renderer=None) -> HitMap:
    """그린 직후에 부른다. 이후 hover/클릭은 이 지도만 본다."""
    r = renderer if renderer is not None else _renderer(fig)
    return HitMap(axes=tuple(_build_axes(fig, ax, i, r)
                             for i, ax in enumerate(fig.axes)),
                  figure=tuple(_build_figure(fig, r)))


def _build_axes(fig, ax, ax_i, r) -> _AxesMap:
    box = _rect(_bbox(ax, r)) or (0.0, 0.0, 0.0, 0.0)

    legend = None
    leg = ax.get_legend()
    if leg is not None and leg.get_visible():
        rect = _rect(_bbox(leg, r))
        if rect:
            legend = Region(*rect,
                            target=Target(kind="legend", path=sel.legend(ax_i),
                                          label="legend", cursor=MOVE,
                                          axes=ax_i, movable=True))

    texts = []
    for which, artist in (("title", ax.title),
                          ("xlabel", ax.xaxis.label),
                          ("ylabel", ax.yaxis.label)):
        if not artist.get_text():
            continue
        rect = _rect(_bbox(artist, r))
        if rect:
            texts.append(Region(*rect, pad=2.0,
                                target=Target(kind="text",
                                              path=sel.text(ax_i, which),
                                              label=which, cursor=MOVE,
                                              axes=ax_i, movable=True,
                                              editable=True)))

    return _AxesMap(index=ax_i, box=box, legend=legend, texts=tuple(texts),
                    axis=tuple(_build_axis_regions(ax, ax_i, r)),
                    layer=Target(kind="layer", path=sel.axes(ax_i),
                                 label=sel.axes(ax_i), axes=ax_i,
                                 cursor=MOVE, movable=True))


def _build_axis_regions(ax, ax_i, r) -> list[Region]:
    out = []
    # 눈금 라벨은 개별 bbox로 둔다. 합집합을 쓰면 양끝 라벨이 튀어나온 만큼
    # 판정 영역이 축 밖으로 부풀어 엉뚱한 클릭을 삼킨다.
    for which, labels in (("x", ax.get_xticklabels()),
                          ("y", ax.get_yticklabels())):
        if not any(t.get_text() for t in labels):
            continue
        target = axis_target(ax_i, which, _label_side(ax, which))
        for t in labels:
            if not t.get_text():
                continue
            rect = _rect(_bbox(t, r))
            if rect:
                out.append(Region(*rect, pad=2.0, target=target))

    for name, spine in ax.spines.items():
        if not spine.get_visible():
            continue
        rect = _rect(_bbox(spine, r))
        if not rect:
            continue
        which = "x" if name in ("bottom", "top") else "y"
        # 축선은 폭이 1px이라 그대로는 누를 수 없다
        out.append(Region(*rect, pad=EDGE_TOL,
                          target=axis_target(ax_i, which, name)))
    return out


def _build_figure(fig, r) -> list[Region]:
    out = []
    sup = getattr(fig, "_suptitle", None)
    if sup is not None and sup.get_text():
        rect = _rect(_bbox(sup, r))
        if rect:
            out.append(Region(*rect, pad=2.0,
                              target=Target(kind="text", path="fig.suptitle",
                                            label="suptitle", cursor=MOVE,
                                            movable=True, editable=True)))
    if getattr(fig, "legends", None):
        leg = fig.legends[0]
        if leg.get_visible():
            rect = _rect(_bbox(leg, r))
            if rect:
                out.append(Region(*rect,
                                  target=Target(kind="legend",
                                                path="fig.legend",
                                                label="figure legend",
                                                cursor=MOVE, movable=True)))
    return out


# --- 편의 함수 (지도를 매번 새로 만든다) --------------------------------------

def hit(fig, tree, x: float, y: float, selected: str | None = None,
        renderer=None) -> list[Target]:
    """지도를 그때그때 만들어 판정한다. 테스트와 일회성 호출용.

    GUI는 draw마다 build()해서 그 지도를 재사용해야 한다 — 매번 만들면
    2패널 그림 기준 한 번에 12ms가 든다.
    """
    m = build(fig, renderer)
    return m.at(x, y, selected=selected, artists=artist_hits(fig, tree, x, y))


def cursor_at(fig, x, y, selected=None, renderer=None) -> str:
    return build(fig, renderer).cursor(x, y, selected=selected)


def artist_hits(fig, tree, x: float, y: float) -> dict:
    """선·점·패치. axes 번호별로 위에 있는 것부터.

    미리 계산할 수 없다 — artist.contains()는 좌표를 받아야 답한다. 그래서
    클릭 때만 부르고 hover에서는 건너뛴다.
    """
    if tree is None:
        return {}
    from matplotlib.backend_bases import MouseEvent

    ev = MouseEvent("pick", fig.canvas, x, y)
    per_axes: dict[int, list] = {}
    for node in tree.walk():
        if not node.pickable or not node.path:
            continue
        try:
            s = sel.parse(node.path)
        except sel.SelectorError:
            continue
        if s.axes is None or s.kind in ("text", "figtext"):
            continue
        try:
            artist = sel.resolve(fig, node.path)
            contains, _ = artist.contains(ev)
        except Exception:
            continue
        if not contains:
            continue
        movable = s.kind == "usertext"
        per_axes.setdefault(s.axes, []).append(
            (getattr(artist, "get_zorder", lambda: 0)(),
             Target(kind="text" if movable else "plot",
                    path=node.path, label=node.label,
                    cursor=MOVE if movable else ARROW,
                    axes=s.axes, movable=movable, editable=movable)))
    return {i: [t for _, t in sorted(v, key=lambda p: -p[0])]
            for i, v in per_axes.items()}
