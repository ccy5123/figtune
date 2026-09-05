"""정규형(canonical form)과 정규화.

figtune의 모든 상태는 정규형으로만 존재한다. 정규형을 정의해 두면 spec 비교,
git diff, 왕복 검증이 전부 기계적으로 가능해진다.

── 무엇을 보장하는가 ────────────────────────────────────────────────
N을 정규화 함수라 할 때:

  (1) 멱등     N(N(x)) = N(x)
  (2) 결정성   같은 내용의 spec은 항상 같은 바이트로 직렬화된다
  (3) 닫힘     모든 조작 op에 대해 op(정규형)은 다시 정규형이다
  (4) 왕복     parse(codegen(N(s))) = N(s)

── 무엇을 보장하지 않는가 ──────────────────────────────────────────
**의미적 최소화는 하지 않는다.** 즉 "그림이 같으면 spec도 같다"는 성립하지
않는다. 그러려면 스크립트가 이미 그린 값과 대조해 중복 override를 지워야
하는데, 그러면 spec이 스크립트 내용에 의존하게 된다. 스크립트가 바뀌는 순간
사용자가 명시한 지정이 조용히 사라진다 — figtune에서 가장 위험한 실패다.

그래서 정규형은 **구문적(syntactic)** 이다. 같은 내용은 같은 표현으로,
다른 내용은 다른 표현으로. 그 이상은 하지 않는다.
─────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Any

from . import props as P
from . import selector as sel
from .spec import Spec, UserText, pyify

CANON_VERSION = "0.1"

# --- 값 별칭표 ------------------------------------------------------------
# matplotlib이 받아들이는 여러 표기를 대표형 하나로 접는다.

LINESTYLE = {"solid": "-", "dashed": "--", "dashdot": "-.", "dotted": ":",
             "None": "none", "none": "none", "": "none", " ": "none"}

MARKER_EMPTY = {"None": "none", "none": "none", "": "none", " ": "none"}

FONTWEIGHT = {"100": "ultralight", "200": "light", "300": "light",
              "400": "normal", "500": "medium", "600": "semibold",
              "700": "bold", "800": "heavy", "900": "black",
              "regular": "normal"}

FONTSTYLE = {"oblique": "italic"}

# matplotlib은 범례 위치에 정수 코드도 받는다
LEGEND_LOC = {0: "best", 1: "upper right", 2: "upper left", 3: "lower left",
              4: "lower right", 5: "center right", 6: "center left",
              7: "center right", 8: "lower center", 9: "upper center",
              10: "center"}

# selector 종류의 적용 순서. 정규 정렬 순서이자 실제 적용 순서다.
# 하나의 표를 apply / codegen / canon이 함께 쓴다.
KIND_ORDER = {"figure": 0, "figtext": 1, "axes": 1, "text": 2, "line": 3, "coll": 3,
              "patch": 3, "txt": 3, "spine": 4, "tick": 5, "grid": 6,
              "usertext": 7, "legend": 9,
              "figlegend": 9}


def path_rank(path: str) -> tuple:
    try:
        s = sel.parse(path)
    except sel.SelectorError:
        return (99, 99, path)
    return (KIND_ORDER.get(s.kind, 8),
            s.axes if s.axes is not None else -1,
            path)


# --- 값 정규화 -------------------------------------------------------------

def value(kind: str, name: str, v: Any) -> Any:
    """프로퍼티 값 하나를 대표형으로 접는다.

    별칭 접기가 형 변환보다 **먼저** 와야 한다. 범례 위치의 정수 코드 2는
    형 변환을 먼저 거치면 문자열 '2'가 되어 별칭표에 걸리지 않고, 그대로
    matplotlib에 넘어가 예외가 난다.
    """
    if v is None:
        return None
    v = pyify(v)

    # 1단계: 별칭 접기 (원본 형 그대로 판단)
    if name == "linestyle":
        v = LINESTYLE.get(str(v), v)
    elif name == "marker":
        v = MARKER_EMPTY.get(str(v), v)
    elif name == "fontweight":
        v = FONTWEIGHT.get(str(v), v)
    elif name == "fontstyle":
        v = FONTSTYLE.get(str(v), v)
    elif name == "loc" and isinstance(v, (int, float)) and not isinstance(v, bool):
        v = LEGEND_LOC.get(int(v), "best")
    elif name == "locator":
        return locator(v)

    # 2단계: 형 변환 (색 hex화, 숫자, tuple2 → list 등)
    v = P.normalize(kind, name, v)
    if v is None:
        return None

    if isinstance(v, float) and v.is_integer() and name in ("ncols",):
        return int(v)
    if isinstance(v, list):
        return [pyify(x) for x in v]
    return v


def locator(d: Any) -> dict | None:
    """locator dict를 키 순서까지 고정한다."""
    if not isinstance(d, dict):
        return None
    k = d.get("kind", "auto")
    if k == "multiple":
        return {"kind": "multiple", "base": float(d["base"])}
    if k == "maxn":
        return {"kind": "maxn", "n": int(d.get("n", 5))}
    if k == "fixed":
        return {"kind": "fixed",
                "values": [float(x) for x in d.get("values", [])]}
    if k in ("null", "autominor", "auto"):
        return {"kind": k}
    return {"kind": "auto"}


# --- spec 정규화 -----------------------------------------------------------

def overrides(raw: dict) -> dict:
    """override 표를 정규 순서·정규 값으로 다시 만든다.

    None과 빈 dict는 제거한다. '명시된 키만 override가 된다'는 원칙상
    None은 애초에 의미가 없고, 남아 있으면 같은 내용이 다르게 직렬화된다.
    """
    out: dict[str, dict] = {}
    for path in sorted(raw, key=path_rank):
        try:
            kind = sel.parse(path).kind
        except sel.SelectorError:
            continue                     # 해석 불가한 selector는 버린다
        props = {}
        for name in sorted(raw[path] or {}):
            v = value(kind, name, raw[path][name])
            if v is not None:
                props[name] = v

        # 범례는 존재 자체가 상태다. 생성된 코드를 되읽으면 '범례를 만든다'는
        # 사실이 visible=True로 복원되므로, 정규형에서도 항상 명시한다.
        # 표현을 빼는 대신 채워서 맞춘다 (빼면 왕복이 어긋난다).
        if kind == "legend" and props and "visible" not in props:
            props["visible"] = True
            props = {k: props[k] for k in sorted(props)}

        if props:
            out[path] = props
    return out


def texts(items: list[UserText]) -> list[UserText]:
    """user text를 (axes, 기존 id) 순으로 정렬하고 id를 다시 매긴다.

    id를 연번으로 다시 매기는 이유: 만들고 지우기를 반복하면 t001, t004처럼
    구멍이 생겨 같은 내용의 spec이 다른 id를 갖게 된다.
    """
    ordered = sorted(items, key=lambda t: (t.axes, t.id))
    out = []
    for i, t in enumerate(ordered, start=1):
        n = UserText(**{**t.__dict__, "id": f"t{i:03d}"})
        n.position = [float(n.position[0]), float(n.position[1])]
        for k in ("fontsize", "rotation", "zorder"):
            v = getattr(n, k)
            if v is not None:
                setattr(n, k, float(v))
        if n.fontweight:
            n.fontweight = FONTWEIGHT.get(str(n.fontweight), n.fontweight)
        if n.color:
            n.color = value("usertext", "color", n.color)
        out.append(n)
    return out


def _remap_text_ids(over: dict, old_new: dict) -> dict:
    out = {}
    for path, props in over.items():
        for old, new in old_new.items():
            if path.endswith(f".text:{old}"):
                path = path[: -len(old)] + new
                break
        out[path] = props
    return out


def spec(s: Spec) -> Spec:
    """spec 전체를 정규형으로 만든다. 멱등이다."""
    new_texts = texts(s.texts)
    old_new = {}
    for old, new in zip(sorted(s.texts, key=lambda t: (t.axes, t.id)), new_texts):
        old_new[old.id] = new.id

    over = _remap_text_ids(dict(s.overrides), old_new)

    return Spec(
        version=s.version,
        script=s.script,
        style_module=s.style_module,
        rcparams={k: pyify(v) for k, v in sorted((s.rcparams or {}).items())},
        overrides=overrides(over),
        fingerprints={k: pyify(s.fingerprints[k])
                      for k in sorted(s.fingerprints or {}, key=path_rank)},
        texts=new_texts,
        data_sources=sorted((pyify(d) for d in (s.data_sources or [])),
                            key=lambda d: d.get("path", "")),
    )


def light(s: Spec) -> Spec:
    """편집 중 쓰는 정규화. override 표만 다시 세운다.

    전체 정규화와의 차이는 **user text id를 다시 매기지 않는다**는 것뿐이다.
    편집 도중 id가 밀리면 GUI가 들고 있는 selector(ax0.text:t002)가 다른
    텍스트를 가리키게 된다. 그래서 id 재부여는 open/save 경계에서만 한다.
    """
    s.overrides = overrides(s.overrides)
    return s


def is_canonical(s: Spec, ids: bool = True) -> bool:
    """정규형인지. ids=False면 id 재부여를 뺀 '편집 중 정규형'을 검사한다."""
    if not ids:
        a = Spec(**{**s.__dict__})
        a.overrides = overrides(dict(s.overrides))
        return a.to_dict() == s.to_dict()
    return _full_is_canonical(s)


def _full_is_canonical(s: Spec) -> bool:
    return spec(s).to_dict() == s.to_dict()


def diff(a: Spec, b: Spec) -> list[str]:
    """두 spec의 차이를 정규형 기준으로 나열한다."""
    na, nb = spec(a).to_dict(), spec(b).to_dict()
    out = []

    def walk(pa, x, y):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                walk(f"{pa}.{k}" if pa else k, x.get(k), y.get(k))
        elif x != y:
            out.append(f"{pa}: {x!r} → {y!r}")

    walk("", na, nb)
    return out
