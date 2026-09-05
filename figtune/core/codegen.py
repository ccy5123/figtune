"""spec → 스타일 모듈 소스.

사용자의 플로팅 코드는 절대 건드리지 않는다. 생성물은 override 문의 나열이며,
사용자 스크립트에는 import 한 줄과 호출 한 줄만 추가된다.

출력은 결정적이다 (정렬 고정). 그래야 git diff가 의미를 가진다.
"""

from __future__ import annotations

from pathlib import Path

from . import props as P
from . import selector as sel
from .spec import Spec

HEADER = '''"""figtune 생성 파일 — {stem}

원본 스크립트: {script}
spec:        {specfile}

이 파일은 figtune이 생성했습니다. 직접 수정해도 되지만, 단순 속성 호출의
나열이라는 형태를 유지해야 figtune이 다시 읽어들일 수 있습니다. 로직(if/for/
변수 대입)을 넣으면 GUI는 이 파일을 읽기 전용으로 전환합니다.
"""

import matplotlib as mpl
from matplotlib import ticker as mticker

RCPARAMS = {rcparams}


def _title_pad(ax, pad):
    """제목 여백만 조정한다. set_title(pad=)는 폰트 속성을 초기화하므로 쓰지 않는다."""
    try:
        ax._set_title_offset_trans(float(pad))
    except AttributeError:
        ax.set_title(ax.get_title(), pad=float(pad),
                     fontsize=ax.title.get_fontsize(),
                     fontweight=ax.title.get_fontweight())


def _fig_legend(fig, **kw):
    """figure 범례를 제자리에서 고친다. 재생성하면 핸들을 잃는다."""
    if not getattr(fig, "legends", None):
        return None
    leg = fig.legends[0]
    if "visible" in kw:
        leg.set_visible(bool(kw["visible"]))
        if not kw["visible"]:
            return leg
    if kw.get("loc") is not None:
        leg.set_loc(kw["loc"])
    if kw.get("bbox_to_anchor") is not None:
        leg.set_bbox_to_anchor(tuple(kw["bbox_to_anchor"]))
    if kw.get("frameon") is not None:
        leg.set_frame_on(bool(kw["frameon"]))
    if kw.get("title") is not None:
        leg.set_title(kw["title"])
    if kw.get("fontsize") is not None:
        for t in leg.get_texts():
            t.set_fontsize(kw["fontsize"])
    if kw.get("title_fontsize") is not None and leg.get_title() is not None:
        leg.get_title().set_fontsize(kw["title_fontsize"])
    return leg


def _legend(ax, labels=None, **kw):
    """범례를 재생성한다.

    seaborn hue 범례는 artist에 label이 없어 get_legend_handles_labels()가
    비어 있다. 그대로 ax.legend()를 부르면 마커가 사라지므로 기존 범례에서
    handle을 회수한다.
    """
    handles, found = ax.get_legend_handles_labels()
    if not handles:
        leg = ax.get_legend()
        if leg is None:
            return None
        handles = list(getattr(leg, "legend_handles", None)
                       or getattr(leg, "legendHandles", []))
        found = [t.get_text() for t in leg.get_texts()]
    if not handles:
        return None
    if labels:
        extra = [h.get_label() for h in handles[len(labels):]]
        found = list(labels)[:len(handles)] + extra
    leg = ax.get_legend()
    if leg is not None and "title" not in kw:
        t = leg.get_title()
        if t is not None and t.get_text():
            kw["title"] = t.get_text()
    return ax.legend(handles, found, **kw)


def apply_style(fig):
    """figure에 figtune 스타일을 적용한다. savefig 직전에 호출하세요."""
'''

FOOTER = """
    return fig
"""

from .canon import KIND_ORDER as _ORDER
from .canon import path_rank as _rank_path

_COORD_TF = {"data": "transData", "axes": "transAxes", "figure": "transFigure"}


def _rank(path: str) -> tuple:
    return _rank_path(path)


_GROUP_NAME = {"figlegend": "legend", "figtext": "texts", "line": "lines", "coll": "collections", "patch": "patches",
               "txt": "texts", "spine": "spines", "tick": "ticks",
               "grid": "grid", "text": "labels", "usertext": "figtune texts"}


def _group_label(s) -> str:
    if s.kind == "figure":
        return "fig"
    base = f"ax{s.axes}"
    if s.kind == "axes":
        return base
    return f"{base}.{_GROUP_NAME.get(s.kind, s.kind)}"


def generate(spec: Spec, specfile: str = "", stem: str = "") -> str:
    from .canon import spec as _canon
    spec = _canon(spec)          # 코드 생성은 정규형에서만 출발한다
    lines: list[str] = []
    used_axes: set[int] = set()

    # 어떤 axes 변수가 필요한지 먼저 수집
    for path in spec.overrides:
        try:
            s = sel.parse(path)
        except sel.SelectorError:
            continue
        if s.axes is not None:
            used_axes.add(s.axes)
    for t in spec.texts:
        used_axes.add(t.axes)

    if used_axes:
        lines.append("    axes = fig.axes")
        for i in sorted(used_axes):
            lines.append(f"    ax{i} = axes[{i}]")
        lines.append("")

    # user text 생성
    if spec.texts:
        lines.append("    # --- figtune 추가 텍스트 ---")
        for t in sorted(spec.texts, key=lambda t: (t.axes, t.id)):
            var = f"ax{t.axes}"
            style = ", ".join(f"{k}={v!r}" for k, v in sorted(t.style().items()))
            tf = f"transform={var}.{_COORD_TF.get(t.coords, 'transAxes')}"
            args = f"{t.position[0]!r}, {t.position[1]!r}, {t.text!r}, {tf}"
            if style:
                args += ", " + style
            lines.append(f"    _t_{t.id} = {var}.text({args})")
            lines.append(f"    _t_{t.id}._figtune_id = {t.id!r}")
        lines.append("")

    # override
    last_group = None
    for path in sorted(spec.overrides, key=_rank):
        over = spec.overrides[path]
        if not over:
            continue
        s = sel.parse(path)
        group = (s.axes, s.kind)
        if group != last_group:
            # 머리말은 묶음 전체를 가리켜야 한다. 첫 경로 이름을 쓰면
            # `# --- ax0.line0 ---` 아래에 line1이 들어가 거짓말이 된다.
            lines.append(f"    # --- {_group_label(s)} ---")
            last_group = group

        if s.kind == "axes" and {"elev", "azim", "roll", "dist_zoom"} & set(over):
            for ln in P.view_code(f"ax{s.axes}", over):
                lines.append(f"    {ln}")
            over = {k: v for k, v in over.items()
                    if k not in ("elev", "azim", "roll", "dist_zoom")}

        if s.kind == "figlegend":
            for ln in P.fig_legend_code(over):
                lines.append(f"    {ln}")
            continue

        if s.kind == "legend":
            for ln in P.legend_code(f"ax{s.axes}", over):
                lines.append(f"    {ln}")
            continue

        for name in sorted(over):
            value = over[name]
            if value is None:
                continue
            try:
                code = P.emit(path, name, value)
            except Exception as exc:                       # pragma: no cover
                lines.append(f"    # !! {path}.{name} 생성 실패: {exc}")
                continue
            for ln in code.split("\n"):
                lines.append(f"    {ln}" if not ln.startswith("    ") else ln)

    if not lines:
        lines.append("    pass")

    body = "\n".join(lines)
    head = HEADER.format(
        stem=stem or Path(spec.style_module).stem or "style",
        script=spec.script or "(미지정)",
        specfile=specfile or "(미지정)",
        rcparams=repr(spec.rcparams) if spec.rcparams else "{}",
    )
    rc = ""
    if spec.rcparams:
        rc = "    mpl.rcParams.update(RCPARAMS)\n"
    return head + rc + body + FOOTER


def write(spec: Spec, out_path: str | Path, specfile: str = "") -> Path:
    out = Path(out_path)
    out.write_text(generate(spec, specfile=specfile, stem=out.stem), encoding="utf-8")
    return out


# --- 사용자 스크립트에 삽입할 두 줄 ---------------------------------------

def hook_lines(style_module_stem: str) -> tuple[str, str]:
    return (f"from {style_module_stem} import apply_style",
            "apply_style(fig)")


def install_hook(script_path: str | Path, style_module_stem: str) -> bool:
    """원본 스크립트에 import/호출 2줄을 추가한다. 이미 있으면 False.

    savefig 앞에 넣는 게 맞지만, 위치 추론이 애매하면 파일 끝에 붙이고
    사용자가 옮기도록 안내한다. 이것이 우리가 사용자 파일을 만지는 유일한
    지점이며, 반드시 사용자 확인을 받은 뒤에만 호출해야 한다.
    """
    p = Path(script_path)
    src = p.read_text(encoding="utf-8")
    imp, call = hook_lines(style_module_stem)
    if imp in src:
        return False
    p.write_text(src.rstrip("\n") + f"\n\n# --- figtune ---\n{imp}\n{call}\n",
                 encoding="utf-8")
    return True
