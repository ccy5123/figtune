"""스타일 모듈 소스 → spec.

우리가 생성한 형식만 읽는다. 포맷 보존이 필요 없으므로 libcst 없이 표준
라이브러리 ast로 충분하다.

핵심 규칙: 이해할 수 없는 문장이 하나라도 나오면 **조용히 무시하지 않는다.**
ParseResult.unhandled에 담아 반환하고, 비어 있지 않으면 GUI가 읽기 전용
모드로 전환한다.
"""

from __future__ import annotations

import ast
import itertools
from dataclasses import dataclass, field
from pathlib import Path

from ..i18n import t as _t
from . import props as P
from .spec import Spec, UserText


@dataclass
class ParseResult:
    spec: Spec
    unhandled: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.unhandled


_TMP_IDS = itertools.count(1)

_LOCATOR_KINDS = {
    "MultipleLocator": lambda a: {"kind": "multiple", "base": a[0]},
    "MaxNLocator": lambda a: {"kind": "maxn", "n": int(a[0])},
    "FixedLocator": lambda a: {"kind": "fixed", "values": list(a[0])},
    "NullLocator": lambda a: {"kind": "null"},
    "AutoMinorLocator": lambda a: {"kind": "autominor"},
    "AutoLocator": lambda a: {"kind": "auto"},
}


def _lit(node):
    return ast.literal_eval(node)


def _target_path(node, axvars: dict[str, int]) -> str | None:
    """AST 표현식 → selector 경로. 모르면 None."""
    if isinstance(node, ast.Name):
        if node.id == "fig":
            return "fig"
        if node.id in axvars:
            return f"ax{axvars[node.id]}"
        return None

    if isinstance(node, ast.Subscript):
        base = _target_path(node.value, axvars)
        if base is None:
            return None
        try:
            key = _lit(node.slice)
        except Exception:
            return None
        if isinstance(key, int):
            if base.endswith(".lines"):
                return base[:-6] + f".line{key}"
            if base.endswith(".collections"):
                return base[:-12] + f".coll{key}"
            if base.endswith(".patches"):
                return base[:-8] + f".patch{key}"
            if base == "fig.texts":
                return f"fig.txt{key}"
            if base.endswith(".texts"):
                return base[:-6] + f".txt{key}"
        if isinstance(key, str) and base.endswith(".spines"):
            return base[:-7] + f".spine:{key}"
        return None

    if isinstance(node, ast.Attribute):
        base = _target_path(node.value, axvars)
        if base is None:
            return None
        a = node.attr
        if a in ("lines", "collections", "patches", "spines", "texts"):
            return f"{base}.{a}"          # 중간 단계
        if a == "_suptitle" and base == "fig":
            return "fig.suptitle"
        if a == "texts" and base == "fig":
            return "fig.texts"
        if a == "title":
            return f"{base}.title"
        if a in ("xaxis", "yaxis"):
            return f"{base}.{a}"
        if a == "label" and base.endswith("axis"):
            return base[:-5] + ("xlabel" if base.endswith("xaxis") else "ylabel")
        return None

    return None


def parse_source(src: str) -> ParseResult:
    spec = Spec()
    un: list[str] = []
    tree = ast.parse(src)

    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == "apply_style"), None)
    if fn is None:
        return ParseResult(spec, [_t("apply_style 함수를 찾을 수 없음")])

    # 모듈 수준 RCPARAMS
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "RCPARAMS":
            try:
                spec.rcparams = _lit(n.value) or {}
            except Exception:
                un.append(_t("RCPARAMS 해석 실패"))

    axvars: dict[str, int] = {}
    textvars: dict[str, str] = {}

    for stmt in fn.body:
        # 문서화 문자열 / pass / return 은 무시
        if isinstance(stmt, (ast.Pass, ast.Return)):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
                and isinstance(stmt.value.value, str):
            continue

        # axN = axes[N]  /  axes = fig.axes
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            tgt = stmt.targets[0]

            if isinstance(tgt, ast.Name) and tgt.id == "axes":
                continue

            if isinstance(tgt, ast.Name) and isinstance(stmt.value, ast.Subscript):
                try:
                    idx = _lit(stmt.value.slice)
                except Exception:
                    idx = None
                if isinstance(idx, int):
                    axvars[tgt.id] = idx
                    continue

            # _t_xxx = axN.text(...)
            if isinstance(tgt, ast.Name) and isinstance(stmt.value, ast.Call) \
                    and isinstance(stmt.value.func, ast.Attribute) \
                    and stmt.value.func.attr == "text":
                t = _parse_usertext(stmt.value, axvars)
                if t is not None:
                    spec.texts.append(t)
                    textvars[tgt.id] = t.id
                    continue

            # axN.xaxis.labelpad = v
            if isinstance(tgt, ast.Attribute) and tgt.attr == "labelpad":
                base = _target_path(tgt.value, axvars)
                if base and base.endswith(("xaxis", "yaxis")):
                    axis = "x" if base.endswith("xaxis") else "y"
                    try:
                        spec.set(base[:-6], f"{axis}labelpad", _lit(stmt.value))
                        continue
                    except Exception:
                        pass

            # _t_xxx._figtune_id = 'tNNN'  → 잠정 id를 진짜 id로 교정한다
            if isinstance(tgt, ast.Attribute) and tgt.attr == "_figtune_id":
                var = getattr(tgt.value, "id", None)
                try:
                    real_id = _lit(stmt.value)
                except Exception:
                    real_id = None
                if var in textvars and isinstance(real_id, str):
                    t = spec.text_by_id(textvars[var])
                    if t is not None:
                        for path in list(spec.overrides):
                            if path.endswith(f".text:{t.id}"):
                                spec.overrides[
                                    path[: -len(t.id)] + real_id] = spec.overrides.pop(path)
                        t.id = real_id
                        textvars[var] = real_id
                continue

            un.append(_t("line {n}: 해석 못 한 대입문", n=stmt.lineno))
            continue

        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
            un.append(_t("line {n}: 단순 호출이 아닌 문장", n=stmt.lineno))
            continue

        ok = _parse_call(stmt.value, spec, axvars)
        if not ok:
            un.append(_t("line {n}: 해석 못 한 호출", n=stmt.lineno))

    from .canon import spec as _canon
    return ParseResult(_canon(spec), un)


def _parse_usertext(call: ast.Call, axvars) -> UserText | None:
    base = _target_path(call.func.value, axvars)
    if base is None or len(call.args) < 3:
        return None
    try:
        x, y, s = _lit(call.args[0]), _lit(call.args[1]), _lit(call.args[2])
    except Exception:
        return None
    ax_i = int(base[2:])
    kw = {}
    coords = "axes"
    for k in call.keywords:
        if k.arg == "transform":
            attr = getattr(k.value, "attr", "")
            coords = {"transData": "data", "transAxes": "axes",
                      "transFigure": "figure"}.get(attr, "axes")
            continue
        try:
            kw[k.arg] = _lit(k.value)
        except Exception:
            pass
    t = UserText(id=f"__tmp{next(_TMP_IDS)}", axes=ax_i, text=s,
                 position=[x, y], coords=coords)
    for k, v in kw.items():
        if hasattr(t, k):
            setattr(t, k, v)
    return t


def _parse_call(call: ast.Call, spec: Spec, axvars) -> bool:
    # _title_pad(axN, pad) — codegen이 내보내는 제목 여백 헬퍼
    if isinstance(call.func, ast.Name) and call.func.id == "_title_pad":
        if len(call.args) != 2:
            return False
        base = _target_path(call.args[0], axvars)
        if base is None:
            return False
        try:
            spec.set(base, "titlepad", _lit(call.args[1]))
        except Exception:
            return False
        return True

    # _title_pos(axN, x, y) — codegen이 내보내는 제목 위치 헬퍼
    if isinstance(call.func, ast.Name) and call.func.id == "_title_pos":
        if len(call.args) != 3:
            return False
        base = _target_path(call.args[0], axvars)
        if base is None:
            return False
        try:
            spec.set(f"{base}.title", "position",
                     [float(_lit(call.args[1])), float(_lit(call.args[2]))])
        except Exception:
            return False
        return True

    # _fig_legend(fig, ...) — figure 수준 범례 헬퍼
    if isinstance(call.func, ast.Name) and call.func.id == "_fig_legend":
        try:
            for k in call.keywords:
                v = _lit(k.value)
                if k.arg == "bbox_to_anchor" and isinstance(v, tuple):
                    v = list(v)
                spec.set("fig.legend", k.arg, v)
        except Exception:
            return False
        return True

    # _legend(axN, ...) — codegen이 내보내는 범례 헬퍼
    if isinstance(call.func, ast.Name) and call.func.id == "_legend":
        if not call.args:
            return False
        base = _target_path(call.args[0], axvars)
        if base is None:
            return False
        try:
            for k in call.keywords:
                v = _lit(k.value)
                if k.arg == "bbox_to_anchor" and isinstance(v, tuple):
                    v = list(v)
                spec.set(f"{base}.legend", k.arg, v)
        except Exception:
            return False
        spec.set(f"{base}.legend", "visible", True)
        return True

    if not isinstance(call.func, ast.Attribute):
        return False
    method = call.func.attr
    base = _target_path(call.func.value, axvars)
    if base is None:
        return False

    def args():
        return [_lit(a) for a in call.args]

    def kwargs():
        return {k.arg: _lit(k.value) for k in call.keywords if k.arg}

    try:
        # locator — 일반 set_XXX보다 먼저 봐야 한다. 인자가 리터럴이 아니라
        # 호출식이므로 generic 분기에 걸리면 literal_eval에서 삼켜진다.
        if method in ("set_major_locator", "set_minor_locator"):
            if not base.endswith(("xaxis", "yaxis")):
                return False
            axis = "x" if base.endswith("xaxis") else "y"
            which = "major" if method == "set_major_locator" else "minor"
            f = call.args[0]
            if not isinstance(f, ast.Call):
                return False
            kindname = getattr(f.func, "attr", getattr(f.func, "id", ""))
            maker = _LOCATOR_KINDS.get(kindname)
            if maker is None:
                return False
            spec.set(f"{base[:-6]}.{axis}tick.{which}", "locator",
                     maker([_lit(a) for a in f.args] or [None]))
            return True

        # set_label_coords(x, y) — 축 라벨 위치. 인자가 둘이라 일반 분기가
        # 삼키지 못하므로 먼저 본다.
        if method == "set_label_coords" and base.endswith(("xaxis", "yaxis")):
            vals = args()
            if len(vals) != 2:
                return False
            which = "xlabel" if base.endswith("xaxis") else "ylabel"
            spec.set(f"{base[:-6]}.{which}", "position",
                     [float(vals[0]), float(vals[1])])
            return True

        # 일반 set_XXX
        if method.startswith("set_") and len(call.args) <= 2 and not call.keywords:
            name = method[4:]
            vals = args()
            if base == "fig" and name == "size_inches":
                spec.set("fig", "size_inches", [float(vals[0]), float(vals[1])])
                return True
            if name == "position" and base.startswith("ax") and ".spine:" in base:
                v = vals[0]
                if isinstance(v, (list, tuple)) and v[0] == "outward":
                    spec.set(base, "position_outward", float(v[1]))
                    return True
                return False
            if name == "edgecolor" and ".spine:" in base:
                spec.set(base, "color", vals[0])
                return True
            if len(vals) == 1:
                v = vals[0]
                if isinstance(v, tuple):
                    v = list(v)
                spec.set(base, name, v)
                return True
            return False

        # set_title(get_title(), pad=)
        if method == "set_title":
            kw = kwargs()
            if "pad" in kw:
                spec.set(base, "titlepad", kw["pad"])
                return True
            return False

        # view_init(elev=, azim=, roll=)
        if method == "view_init":
            for k, v in kwargs().items():
                if k in ("elev", "azim", "roll"):
                    spec.set(base, k, v)
            return True

        if method == "set_box_aspect":
            kw = kwargs()
            if "zoom" in kw:
                spec.set(base, "dist_zoom", kw["zoom"])
                return True
            return False

        # tick_params
        if method == "tick_params":
            kw = kwargs()
            axis = kw.pop("axis", "both")
            which = kw.pop("which", "major")
            if axis == "both":
                axis_list = ["x", "y"]
            else:
                axis_list = [axis]
            for a in axis_list:
                for k, v in kw.items():
                    spec.set(f"{base}.{a}tick.{which}", k, v)
            return True

        # grid
        if method == "grid":
            kw = kwargs()
            axis = kw.pop("axis", "both")
            kw.pop("which", None)
            vis = args()[0] if call.args else kw.pop("visible", True)
            axis_list = ["x", "y"] if axis == "both" else [axis]
            for a in axis_list:
                spec.set(f"{base}.grid.{a}", "visible", bool(vis))
                for k, v in kw.items():
                    spec.set(f"{base}.grid.{a}", k, v)
            return True

        # legend
        if method == "legend":
            kw = kwargs()
            for k, v in kw.items():
                if k in ("bbox_to_anchor",) and isinstance(v, tuple):
                    v = list(v)
                spec.set(f"{base}.legend", k, v)
            spec.set(f"{base}.legend", "visible", True)
            return True

    except Exception:
        return False

    return False


def parse_file(path: str | Path) -> ParseResult:
    return parse_source(Path(path).read_text(encoding="utf-8"))
