"""프로퍼티 레지스트리.

GUI 위젯 생성, 라이브 적용, 코드 생성, 코드 파싱이 전부 이 모듈을 참조한다.
속성을 하나 추가하려면 여기만 고치면 된다.

값은 항상 YAML로 직렬화 가능한 리터럴이다 (str/int/float/bool/list/dict/None).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import matplotlib as mpl
from matplotlib import ticker as mticker
from matplotlib.colors import to_hex

from . import selector as sel

# --- 프로퍼티 기술 --------------------------------------------------------


@dataclass(frozen=True)
class Prop:
    name: str
    kind: str                      # color|float|int|str|bool|choice|tuple2|locator|strlist
    label: str = ""                # GUI 표시명
    choices: tuple = ()
    lo: float | None = None
    hi: float | None = None
    step: float | None = None

    def __post_init__(self):
        if not self.label:
            object.__setattr__(self, "label", self.name)


def P(name, kind, label="", choices=(), lo=None, hi=None, step=None) -> Prop:
    return Prop(name, kind, label, tuple(choices), lo, hi, step)


FONT_WEIGHTS = ("normal", "bold", "light", "heavy")
FONT_STYLES = ("normal", "italic", "oblique")
LINESTYLES = ("-", "--", "-.", ":", "none")
MARKERS = ("none", ".", "o", "s", "^", "v", "D", "x", "+", "*")
HA = ("left", "center", "right")
VA = ("top", "center", "bottom", "baseline")
LEGEND_LOCS = ("best", "upper right", "upper left", "lower left", "lower right",
               "center left", "center right", "upper center", "lower center", "center")

# --- 레지스트리 -----------------------------------------------------------

REGISTRY: dict[str, list[Prop]] = {
    "figure": [
        P("size_inches", "tuple2", "크기 (in)", lo=1, hi=30, step=0.1),
        P("dpi", "int", "DPI", lo=50, hi=1200, step=10),
        P("facecolor", "color", "배경색"),
    ],
    "axes": [
        P("xlim", "tuple2", "x 범위"),
        P("ylim", "tuple2", "y 범위"),
        P("xscale", "choice", "x 스케일", choices=("linear", "log", "symlog")),
        P("yscale", "choice", "y 스케일", choices=("linear", "log", "symlog")),
        P("facecolor", "color", "배경색"),
        P("titlepad", "float", "제목 여백", lo=-20, hi=40, step=0.5),
        P("xlabelpad", "float", "x라벨 여백", lo=-20, hi=40, step=0.5),
        P("ylabelpad", "float", "y라벨 여백", lo=-20, hi=40, step=0.5),
    ],
    "axes3d": [
        P("elev", "float", "고도각", lo=-90, hi=90, step=1),
        P("azim", "float", "방위각", lo=-180, hi=180, step=1),
        P("roll", "float", "롤", lo=-180, hi=180, step=1),
        P("dist_zoom", "float", "확대", lo=0.2, hi=5, step=0.05),
    ],
    "text": [
        P("text", "str", "내용"),
        P("fontsize", "float", "크기", lo=1, hi=72, step=0.5),
        P("color", "color", "색"),
        P("fontfamily", "str", "글꼴"),
        P("fontweight", "choice", "굵기", choices=FONT_WEIGHTS),
        P("fontstyle", "choice", "기울임", choices=FONT_STYLES),
        P("rotation", "float", "회전", lo=-180, hi=180, step=1),
        P("horizontalalignment", "choice", "가로 정렬", choices=HA),
        P("verticalalignment", "choice", "세로 정렬", choices=VA),
    ],
    "figlegend": [
        P("visible", "bool", "표시"),
        P("loc", "choice", "위치", choices=LEGEND_LOCS),
        P("bbox_to_anchor", "tuple2", "앵커"),
        P("frameon", "bool", "테두리"),
        P("fontsize", "float", "글자 크기", lo=1, hi=40, step=0.5),
        P("title", "str", "범례 제목"),
        P("title_fontsize", "float", "제목 크기", lo=1, hi=40, step=0.5),
    ],
    "figtext": [
        P("text", "str", "내용"),
        P("position", "tuple2", "위치"),
        P("fontsize", "float", "크기", lo=1, hi=72, step=0.5),
        P("color", "color", "색"),
        P("fontfamily", "str", "글꼴"),
        P("fontweight", "choice", "굵기", choices=FONT_WEIGHTS),
        P("fontstyle", "choice", "기울임", choices=FONT_STYLES),
        P("horizontalalignment", "choice", "가로 정렬", choices=HA),
        P("verticalalignment", "choice", "세로 정렬", choices=VA),
        P("visible", "bool", "표시"),
    ],
    "txt": [
        P("text", "str", "내용"),
        P("position", "tuple2", "위치"),
        P("fontsize", "float", "크기", lo=1, hi=72, step=0.5),
        P("color", "color", "색"),
        P("fontfamily", "str", "글꼴"),
        P("fontweight", "choice", "굵기", choices=FONT_WEIGHTS),
        P("fontstyle", "choice", "기울임", choices=FONT_STYLES),
        P("rotation", "float", "회전", lo=-180, hi=180, step=1),
        P("horizontalalignment", "choice", "가로 정렬", choices=HA),
        P("verticalalignment", "choice", "세로 정렬", choices=VA),
        P("visible", "bool", "표시"),
        P("zorder", "float", "z순서", lo=0, hi=100, step=1),
    ],
    "usertext": [
        P("text", "str", "내용"),
        P("position", "tuple2", "위치"),
        P("fontsize", "float", "크기", lo=1, hi=72, step=0.5),
        P("color", "color", "색"),
        P("fontfamily", "str", "글꼴"),
        P("fontweight", "choice", "굵기", choices=FONT_WEIGHTS),
        P("fontstyle", "choice", "기울임", choices=FONT_STYLES),
        P("rotation", "float", "회전", lo=-180, hi=180, step=1),
        P("horizontalalignment", "choice", "가로 정렬", choices=HA),
        P("verticalalignment", "choice", "세로 정렬", choices=VA),
        P("zorder", "float", "z순서", lo=0, hi=100, step=1),
    ],
    "line": [
        P("color", "color", "선 색"),
        P("linewidth", "float", "선 두께", lo=0, hi=10, step=0.1),
        P("linestyle", "choice", "선 종류", choices=LINESTYLES),
        P("marker", "choice", "마커", choices=MARKERS),
        P("markersize", "float", "마커 크기", lo=0, hi=30, step=0.5),
        P("markerfacecolor", "color", "마커 내부색"),
        P("markeredgecolor", "color", "마커 테두리색"),
        P("markeredgewidth", "float", "마커 테두리", lo=0, hi=6, step=0.1),
        P("alpha", "float", "투명도", lo=0, hi=1, step=0.05),
        P("zorder", "float", "z순서", lo=0, hi=100, step=1),
        P("label", "str", "범례 라벨"),
    ],
    "coll": [
        P("facecolor", "color", "채움색"),
        P("edgecolor", "color", "테두리색"),
        P("linewidth", "float", "테두리 두께", lo=0, hi=10, step=0.1),
        P("alpha", "float", "투명도", lo=0, hi=1, step=0.05),
        P("sizes", "floatlist", "마커 크기"),
        P("zorder", "float", "z순서", lo=0, hi=100, step=1),
        P("label", "str", "범례 라벨"),
    ],
    "patch": [
        P("facecolor", "color", "채움색"),
        P("edgecolor", "color", "테두리색"),
        P("linewidth", "float", "테두리 두께", lo=0, hi=10, step=0.1),
        P("alpha", "float", "투명도", lo=0, hi=1, step=0.05),
        P("zorder", "float", "z순서", lo=0, hi=100, step=1),
    ],
    "spine": [
        P("visible", "bool", "표시"),
        P("linewidth", "float", "두께", lo=0, hi=6, step=0.1),
        P("color", "color", "색"),
        P("position_outward", "float", "바깥 오프셋", lo=-30, hi=30, step=1),
    ],
    "tick": [
        P("labelsize", "float", "라벨 크기", lo=1, hi=40, step=0.5),
        P("direction", "choice", "방향", choices=("out", "in", "inout")),
        P("length", "float", "길이", lo=0, hi=20, step=0.5),
        P("width", "float", "두께", lo=0, hi=6, step=0.1),
        P("pad", "float", "여백", lo=0, hi=30, step=0.5),
        P("color", "color", "눈금색"),
        P("labelcolor", "color", "라벨색"),
        P("labelrotation", "float", "라벨 회전", lo=-180, hi=180, step=5),
        P("bottom", "bool", "아래 표시"),
        P("top", "bool", "위 표시"),
        P("left", "bool", "왼쪽 표시"),
        P("right", "bool", "오른쪽 표시"),
        P("locator", "locator", "눈금 간격"),
    ],
    "grid": [
        P("visible", "bool", "표시"),
        P("which", "choice", "대상", choices=("major", "minor", "both")),
        P("linewidth", "float", "두께", lo=0, hi=5, step=0.1),
        P("linestyle", "choice", "선 종류", choices=LINESTYLES),
        P("color", "color", "색"),
        P("alpha", "float", "투명도", lo=0, hi=1, step=0.05),
    ],
    "legend": [
        P("visible", "bool", "표시"),
        P("loc", "choice", "위치", choices=LEGEND_LOCS),
        P("bbox_to_anchor", "tuple2", "앵커"),
        P("frameon", "bool", "테두리"),
        P("fontsize", "float", "글자 크기", lo=1, hi=40, step=0.5),
        P("ncols", "int", "열 수", lo=1, hi=8, step=1),
        P("title", "str", "범례 제목"),
        P("labelspacing", "float", "항목 간격", lo=0, hi=3, step=0.05),
        P("labels", "strlist", "라벨"),
    ],
}

COLOR_PROPS = {p.name for props in REGISTRY.values() for p in props if p.kind == "color"}


def props_for(kind: str) -> list[Prop]:
    return REGISTRY.get(kind, [])


def is_3d(fig, path: str) -> bool:
    try:
        s = sel.parse(path)
        return s.axes is not None and hasattr(fig.axes[s.axes], "zaxis")
    except Exception:
        return False


def props_for_path(fig, path: str) -> list[Prop]:
    """3D axes면 시점 조작 속성을 덧붙인다."""
    kind = sel.parse(path).kind
    out = list(REGISTRY.get(kind, []))
    if kind == "axes" and is_3d(fig, path):
        out += REGISTRY["axes3d"]
    return out


_VIEW_KEYS = ("elev", "azim", "roll")


def apply_view(ax, over: dict) -> None:
    """3D 시점을 한 번에 적용한다.

    ax.view_init(azim=30)처럼 일부만 주면 나머지가 초기값으로 되돌아간다.
    범례와 제목 여백에서 겪은 것과 같은 함정이라, 여기서도 배치로 적용한다.
    """
    kw = {k: over[k] for k in _VIEW_KEYS if over.get(k) is not None}
    if kw:
        ax.view_init(elev=kw.get("elev", ax.elev),
                     azim=kw.get("azim", ax.azim),
                     roll=kw.get("roll", getattr(ax, "roll", 0)))
    z = over.get("dist_zoom")
    if z:
        try:
            ax.set_box_aspect(None, zoom=float(z))
        except TypeError:                     # pragma: no cover - 구버전
            pass


def view_code(var: str, over: dict) -> list[str]:
    kw = {k: over[k] for k in _VIEW_KEYS if over.get(k) is not None}
    lines = []
    if kw:
        parts = ", ".join(f"{k}={v!r}" for k, v in sorted(kw.items()))
        lines.append(f"{var}.view_init({parts})")
    if over.get("dist_zoom"):
        lines.append(f"{var}.set_box_aspect(None, zoom={float(over['dist_zoom'])!r})")
    return lines


def prop_of(kind: str, name: str) -> Prop | None:
    for p in REGISTRY.get(kind, []):
        if p.name == name:
            return p
    return None


# --- 값 정규화 ------------------------------------------------------------

def normalize(kind: str, name: str, value: Any) -> Any:
    """YAML 직렬화 가능한 리터럴로 정규화."""
    if value is None:
        return None
    p = prop_of(kind, name)
    if p is None:
        return value
    if p.kind == "color":
        try:
            return to_hex(value, keep_alpha=False)
        except (ValueError, TypeError):
            return None
    if p.kind == "tuple2":
        try:
            return [float(value[0]), float(value[1])]
        except (TypeError, ValueError, IndexError):
            return None
    if p.kind in ("float",):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if p.kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if p.kind == "bool":
        return bool(value)
    if p.kind == "floatlist":
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return None
    if p.kind == "strlist":
        try:
            return [str(v) for v in value]
        except TypeError:
            return None
    if p.kind == "str":
        return None if value is None else str(value)
    if p.kind == "choice":
        return str(value)
    return value


# --- locator 인코딩 -------------------------------------------------------

def encode_locator(loc) -> dict | None:
    if isinstance(loc, mticker.MultipleLocator):
        # matplotlib 버전별 속성명 차이 흡수
        base = getattr(getattr(loc, "_edge", None), "step", None)
        if base is None:
            base = getattr(loc, "_base", None)
            base = getattr(base, "_base", base)
        return {"kind": "multiple", "base": float(base)} if base else None
    if isinstance(loc, mticker.MaxNLocator):
        n = getattr(loc, "_nbins", None)
        return {"kind": "maxn", "n": int(n)} if isinstance(n, int) else {"kind": "auto"}
    if isinstance(loc, mticker.FixedLocator):
        return {"kind": "fixed", "values": [float(v) for v in loc.locs]}
    if isinstance(loc, mticker.NullLocator):
        return {"kind": "null"}
    if isinstance(loc, mticker.AutoMinorLocator):
        return {"kind": "autominor"}
    return {"kind": "auto"}


def decode_locator(d: dict | None):
    if not d:
        return None
    k = d.get("kind")
    if k == "multiple":
        return mticker.MultipleLocator(float(d["base"]))
    if k == "maxn":
        return mticker.MaxNLocator(int(d.get("n", 5)))
    if k == "fixed":
        return mticker.FixedLocator([float(v) for v in d.get("values", [])])
    if k == "null":
        return mticker.NullLocator()
    if k == "autominor":
        return mticker.AutoMinorLocator()
    return mticker.AutoLocator()


def locator_code(d: dict | None) -> str | None:
    if not d:
        return None
    k = d.get("kind")
    if k == "multiple":
        return f"mticker.MultipleLocator({float(d['base'])!r})"
    if k == "maxn":
        return f"mticker.MaxNLocator({int(d.get('n', 5))})"
    if k == "fixed":
        return f"mticker.FixedLocator({[float(v) for v in d.get('values', [])]!r})"
    if k == "null":
        return "mticker.NullLocator()"
    if k == "autominor":
        return "mticker.AutoMinorLocator()"
    return "mticker.AutoLocator()"


# --- 축 레벨 특수 프로퍼티 ------------------------------------------------

def _axes_get(ax, name):
    if name in ("elev", "azim", "roll"):
        return getattr(ax, name, None)
    if name == "dist_zoom":
        return None
    if name == "titlepad":
        return getattr(ax.title, "_figtune_pad", mpl.rcParams["axes.titlepad"])
    if name == "xlabelpad":
        return ax.xaxis.labelpad
    if name == "ylabelpad":
        return ax.yaxis.labelpad
    if name in ("xlim", "ylim"):
        return list(getattr(ax, f"get_{name}")())
    return getattr(ax, f"get_{name}")()


def set_title_pad(ax, pad) -> None:
    """제목 여백만 바꾼다.

    ax.set_title(text, pad=…)를 쓰면 안 된다. matplotlib 내부에서
    title.update(default)를 호출해 fontsize/fontweight를 rcParams 기본값으로
    되돌리기 때문이다. 그러면 '굵게 → 여백' 순으로 편집했을 때 굵기가 조용히
    사라지고, 편집 중 화면과 재실행 결과가 달라진다.
    """
    pad = float(pad)
    try:
        ax._set_title_offset_trans(pad)
    except AttributeError:                      # pragma: no cover - 구버전 대비
        keep = {}
        for k in ("fontsize", "fontweight", "color", "fontstyle"):
            try:
                keep[k] = getattr(ax.title, f"get_{k}")()
            except Exception:
                pass
        ax.set_title(ax.get_title(), pad=pad, **keep)
    ax.title._figtune_pad = pad


def _axes_set(ax, name, value):
    if name == "titlepad":
        set_title_pad(ax, value)
        return
    if name == "xlabelpad":
        ax.xaxis.labelpad = value
        return
    if name == "ylabelpad":
        ax.yaxis.labelpad = value
        return
    getattr(ax, f"set_{name}")(value)


def _axes_code(var, name, value):
    if name == "titlepad":
        return f"_title_pad({var}, {float(value)!r})"
    if name in ("xlabelpad", "ylabelpad"):
        return f"{var}.{name[0]}axis.labelpad = {value!r}"
    return f"{var}.set_{name}({value!r})"


# --- spine 특수 ------------------------------------------------------------

def _spine_get(sp, name):
    if name == "position_outward":
        pos = sp.get_position()
        if isinstance(pos, tuple) and pos[0] == "outward":
            return float(pos[1])
        return 0.0
    if name == "color":
        return sp.get_edgecolor()
    return getattr(sp, f"get_{name}")()


def _spine_set(sp, name, value):
    if name == "position_outward":
        sp.set_position(("outward", float(value)))
        return
    if name == "color":
        sp.set_edgecolor(value)
        return
    getattr(sp, f"set_{name}")(value)


def _spine_code(var, name, value):
    if name == "position_outward":
        return f"{var}.set_position(('outward', {float(value)!r}))"
    if name == "color":
        return f"{var}.set_edgecolor({value!r})"
    return f"{var}.set_{name}({value!r})"


# --- 일반 artist ----------------------------------------------------------

_ALIAS_GET = {
    "fontfamily": "get_fontfamily",
    "horizontalalignment": "get_horizontalalignment",
    "verticalalignment": "get_verticalalignment",
    "size_inches": "get_size_inches",
}


def _artist_get(obj, name):
    getter = _ALIAS_GET.get(name, f"get_{name}")
    val = getattr(obj, getter)()
    if name == "fontfamily" and isinstance(val, (list, tuple)):
        val = val[0] if val else None
    return val


def _artist_set(obj, name, value):
    getattr(obj, f"set_{name}")(value)


# --- 공개 API -------------------------------------------------------------

def get(fig, path: str, name: str) -> Any:
    """현재 값을 읽는다. 읽을 수 없으면 None."""
    s = sel.parse(path)
    try:
        if s.kind == "figlegend":
            return normalize(s.kind, name, _fig_legend_get(fig, name))
        if s.kind == "tick":
            return _tick_get(fig.axes[s.axes], s.name, s.which, name)
        if s.kind == "grid":
            return _grid_get(fig.axes[s.axes], s.name, name)
        if s.kind == "legend":
            return _legend_get(fig.axes[s.axes], name)
        obj = sel.resolve(fig, path)
        if s.kind == "axes":
            raw = _axes_get(obj, name)
        elif s.kind == "spine":
            raw = _spine_get(obj, name)
        else:
            raw = _artist_get(obj, name)
        return normalize(s.kind, name, raw)
    except Exception:
        return None


def apply(fig, path: str, name: str, value: Any) -> None:
    """살아있는 Figure에 값을 적용한다."""
    s = sel.parse(path)
    if s.kind == "figlegend":
        apply_fig_legend(fig, {name: value})
        return
    if s.kind == "tick":
        _tick_set(fig.axes[s.axes], s.name, s.which, name, value)
        return
    if s.kind == "grid":
        _grid_set(fig.axes[s.axes], s.name, name, value)
        return
    if s.kind == "legend":
        _legend_set(fig.axes[s.axes], name, value)
        return
    if s.kind == "figure" and name == "dpi":
        # dpi는 '출력 해상도'다. 화면 표시 배율(display dpi)과 물리적으로 같은
        # 속성이라 라이브 figure에 그대로 적용하면 캔버스 크기가 튄다.
        # spec에는 기록하되 적용은 export 시점에만 한다.
        return
    obj = sel.resolve(fig, path)
    if s.kind == "axes":
        if name in _VIEW_KEYS or name == "dist_zoom":
            apply_view(obj, {name: value})
            return
        _axes_set(obj, name, value)
    elif s.kind == "spine":
        _spine_set(obj, name, value)
    elif s.kind == "figure" and name == "size_inches":
        obj.set_size_inches(*value)
    else:
        _artist_set(obj, name, value)


def emit(path: str, name: str, value: Any) -> str:
    """override 한 줄의 Python 소스를 만든다."""
    s = sel.parse(path)
    if s.kind == "figlegend":
        return fig_legend_code({name: value})[0]
    if s.kind == "tick":
        return _tick_code(f"ax{s.axes}", s.name, s.which, name, value)
    if s.kind == "grid":
        return _grid_code(f"ax{s.axes}", s.name, name, value)
    if s.kind == "legend":
        return _legend_code(f"ax{s.axes}", name, value)
    var = sel.code_expr(path)
    if s.kind == "axes":
        if name in _VIEW_KEYS or name == "dist_zoom":
            return view_code(var, {name: value})[0]
        return _axes_code(var, name, value)
    if s.kind == "spine":
        return _spine_code(var, name, value)
    if s.kind == "figure" and name == "size_inches":
        return f"fig.set_size_inches({float(value[0])!r}, {float(value[1])!r})"
    if isinstance(value, list) and prop_of(s.kind, name) and \
            prop_of(s.kind, name).kind == "tuple2":
        return f"{var}.set_{name}(({value[0]!r}, {value[1]!r}))"
    return f"{var}.set_{name}({value!r})"


# --- tick -----------------------------------------------------------------

_TICK_SIDES = {"x": ("bottom", "top"), "y": ("left", "right")}


def _tick_get(ax, axis, which, name):
    if name == "locator":
        a = ax.xaxis if axis == "x" else ax.yaxis
        loc = a.get_major_locator() if which == "major" else a.get_minor_locator()
        return encode_locator(loc)
    a = ax.xaxis if axis == "x" else ax.yaxis
    ticks = a.get_major_ticks() if which == "major" else a.get_minor_ticks()
    if not ticks:
        return None
    t = ticks[0]
    try:
        if name == "labelsize":
            return float(t.label1.get_fontsize())
        if name == "length":
            return float(t.tick1line.get_markersize())
        if name == "width":
            return float(t.tick1line.get_markeredgewidth())
        if name == "pad":
            return float(t.get_pad())
        if name == "color":
            return to_hex(t.tick1line.get_color())
        if name == "labelcolor":
            return to_hex(t.label1.get_color())
        if name in ("bottom", "left"):
            return bool(t.tick1line.get_visible())
        if name in ("top", "right"):
            return bool(t.tick2line.get_visible())
    except Exception:
        return None
    return None


def _tick_set(ax, axis, which, name, value):
    if name == "locator":
        a = ax.xaxis if axis == "x" else ax.yaxis
        loc = decode_locator(value)
        if loc is not None:
            (a.set_major_locator if which == "major" else a.set_minor_locator)(loc)
        return
    ax.tick_params(axis=axis, which=which, **{name: value})


def _tick_code(var, axis, which, name, value):
    if name == "locator":
        code = locator_code(value)
        setter = "set_major_locator" if which == "major" else "set_minor_locator"
        return f"{var}.{axis}axis.{setter}({code})"
    return f"{var}.tick_params(axis={axis!r}, which={which!r}, {name}={value!r})"


# --- grid -----------------------------------------------------------------

def _grid_get(ax, axis, name):
    lines = ax.get_xgridlines() if axis == "x" else ax.get_ygridlines()
    if name == "visible":
        return bool(lines) and any(l.get_visible() for l in lines)
    if not lines:
        return None
    l = lines[0]
    try:
        if name == "color":
            return to_hex(l.get_color())
        if name == "linewidth":
            return float(l.get_linewidth())
        if name == "linestyle":
            return l.get_linestyle()
        if name == "alpha":
            a = l.get_alpha()
            return None if a is None else float(a)
    except Exception:
        return None
    return None


def _grid_set(ax, axis, name, value):
    if name == "visible":
        ax.grid(bool(value), axis=axis)
        return
    if name == "which":
        return
    ax.grid(True, axis=axis, **{name: value})


def _grid_code(var, axis, name, value):
    if name == "visible":
        return f"{var}.grid({bool(value)!r}, axis={axis!r})"
    return f"{var}.grid(True, axis={axis!r}, {name}={value!r})"


# --- legend ---------------------------------------------------------------

_LEGEND_KW = ("loc", "bbox_to_anchor", "frameon", "fontsize", "ncols",
              "title", "labelspacing", "labels")


def _decode_loc(leg):
    """matplotlib은 loc을 정수 코드로 들고 있다. 사람이 읽는 이름으로 되돌린다.

    사용자가 loc=(0.2, 0.7)처럼 좌표를 직접 준 경우는 이름이 없다. 그때는
    None을 돌려준다 — 없는 이름을 지어내면 드롭다운이 거짓말을 한다.
    """
    from matplotlib.legend import Legend

    raw = getattr(leg, "_loc", None)
    if isinstance(raw, str):
        return raw if raw in Legend.codes else None
    for name, code in Legend.codes.items():
        if raw == code:
            return name
    return None


def _legend_get(ax, name):
    leg = ax.get_legend()
    if name == "visible":
        return leg is not None and leg.get_visible()
    if leg is None:
        return None
    try:
        if name == "loc":
            return _decode_loc(leg)
        if name == "frameon":
            return bool(leg.get_frame_on())
        if name == "title":
            t = leg.get_title()
            return t.get_text() if t is not None else None
        if name == "fontsize":
            texts = leg.get_texts()
            return float(texts[0].get_fontsize()) if texts else None
        if name == "labels":
            return [t.get_text() for t in leg.get_texts()]
        if name == "ncols":
            return int(getattr(leg, "_ncols", 1))
    except Exception:
        return None
    return None


def _legend_set(ax, name, value):
    """단일 prop 폴백. 범례는 재생성되므로 반드시 apply_legend를 쓸 것."""
    apply_legend(ax, {name: value})


def apply_legend(ax, over: dict) -> None:
    """범례 override 전체를 한 번에 적용한다.

    ax.legend()는 호출할 때마다 범례를 새로 만든다. 따라서 prop 하나씩
    적용하면 직전 설정이 소실된다. spec에 있는 범례 override를 모아
    단 한 번 호출해야 한다.
    """
    if over.get("visible") is False:
        leg = ax.get_legend()
        if leg is not None:
            leg.set_visible(False)
        return

    kw = {k: v for k, v in over.items()
          if k in _LEGEND_KW and k != "labels" and v is not None}
    if "bbox_to_anchor" in kw:
        kw["bbox_to_anchor"] = tuple(kw["bbox_to_anchor"])

    # 범례가 없는 축에 override를 걸었다고 새로 만들면 안 된다. seaborn
    # FacetGrid처럼 범례가 figure 수준에 있는 경우, 패널 안에 엉뚱한 범례가
    # 하나 더 생긴다. 사용자가 요청하지 않은 변경이다.
    # 새로 만들려면 visible=True를 명시해야 한다.
    if ax.get_legend() is None and not over.get("visible"):
        return

    handles, labels = legend_handles(ax)
    if not handles:
        return
    if over.get("labels"):
        labels = list(over["labels"])[:len(handles)]
        labels += [h.get_label() for h in handles[len(labels):]]
    leg = ax.get_legend()
    if leg is not None and "title" not in kw:
        t = leg.get_title()
        if t is not None and t.get_text():
            kw["title"] = t.get_text()
    ax.legend(handles, labels, **kw)


def apply_fig_legend(fig, over: dict) -> None:
    """figure 범례를 **제자리에서** 고친다.

    축 범례처럼 재생성하면 seaborn이 FacetGrid에 달아둔 핸들을 잃는다.
    Legend 객체는 loc·bbox·frame·title을 직접 바꿀 수 있으므로 그쪽을 쓴다.
    없는 범례를 만들지는 않는다.
    """
    legs = getattr(fig, "legends", None)
    if not legs:
        return
    leg = legs[0]
    if "visible" in over:
        leg.set_visible(bool(over["visible"]))
        if not over["visible"]:
            return
    if over.get("loc") is not None:
        leg.set_loc(over["loc"])
    if over.get("bbox_to_anchor") is not None:
        leg.set_bbox_to_anchor(tuple(over["bbox_to_anchor"]))
    if over.get("frameon") is not None:
        leg.set_frame_on(bool(over["frameon"]))
    if over.get("title") is not None:
        leg.set_title(over["title"])
    if over.get("fontsize") is not None:
        for t in leg.get_texts():
            t.set_fontsize(over["fontsize"])
    if over.get("title_fontsize") is not None:
        t = leg.get_title()
        if t is not None:
            t.set_fontsize(over["title_fontsize"])


def fig_legend_code(over: dict) -> list[str]:
    parts = ", ".join(f"{k}={v!r}" for k, v in sorted(over.items())
                      if v is not None)
    return [f"_fig_legend(fig, {parts})" if parts else "_fig_legend(fig)"]


def _fig_legend_get(fig, name):
    legs = getattr(fig, "legends", None)
    if not legs:
        return None
    leg = legs[0]
    try:
        if name == "visible":
            return bool(leg.get_visible())
        if name == "loc":
            return _decode_loc(leg)
        if name == "frameon":
            return bool(leg.get_frame_on())
        if name == "title":
            t = leg.get_title()
            return t.get_text() if t is not None else None
        if name == "title_fontsize":
            t = leg.get_title()
            return float(t.get_fontsize()) if t is not None else None
        if name == "fontsize":
            ts = leg.get_texts()
            return float(ts[0].get_fontsize()) if ts else None
    except Exception:
        return None
    return None


def legend_handles(ax):
    """범례 handle/label을 얻는다.

    seaborn의 hue 범례는 artist에 label이 붙지 않아
    get_legend_handles_labels()가 빈 목록을 준다. 그대로 재생성하면 마커가
    사라지므로, 이미 만들어진 범례에서 handle을 회수한다.
    """
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        return handles, labels
    leg = ax.get_legend()
    if leg is None:
        return [], []
    handles = list(getattr(leg, "legend_handles", None)
                   or getattr(leg, "legendHandles", []))
    labels = [t.get_text() for t in leg.get_texts()]
    return handles, labels


def legend_code(var: str, over: dict) -> list[str]:
    """범례 override 전체에 대한 코드 줄들."""
    if over.get("visible") is False:
        return [f"_leg = {var}.get_legend()",
                f"if _leg is not None:",
                f"    _leg.set_visible(False)"]
    kw = {k: v for k, v in over.items()
          if k in _LEGEND_KW and k != "labels" and v is not None}
    if "bbox_to_anchor" in kw:
        kw["bbox_to_anchor"] = tuple(kw["bbox_to_anchor"])
    if over.get("labels"):
        kw["labels"] = list(over["labels"])
    parts = ", ".join(f"{k}={v!r}" for k, v in sorted(kw.items()))
    return [f"_legend({var}, {parts})" if parts else f"_legend({var})"]


def _legend_code(var, name, value):
    return legend_code(var, {name: value})[0]
