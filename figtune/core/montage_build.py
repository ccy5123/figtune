"""여러 스크립트의 figure를 하나로 합치는 상위 API.

각 패널은 자기 스크립트와 spec을 그대로 유지한다. montage는 그것들을
참조하는 별도 문서일 뿐이므로, 패널 하나를 고치면 다시 합치기만 하면 된다.
figtune의 전제("원본 코드를 구조적으로 건드리지 않는다")가 유지된다.
"""

from __future__ import annotations

import io
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from ..i18n import t as _t
from . import inline
from . import montage as M
from .spec import Spec


@dataclass
class PanelRef:
    script: str
    spec: str = ""              # .figtune.yaml 경로. 비우면 스크립트 옆 기본값
    axes_index: int = 0         # 어느 axes를 정렬 기준으로 삼을지
    label: str = ""
    # 격자에서 차지할 자리. row/col이 None이면 남은 칸에 읽는 순서로 놓는다.
    # 균일 격자만으로는 논문 그림을 못 만든다 — 3x2에서 2칸짜리 둘과
    # 1칸짜리 둘 같은 조합이 실제로 필요하다.
    row: int | None = None
    col: int | None = None
    rowspan: int = 1
    colspan: int = 1

    def resolve(self, base: Path) -> tuple[Path, Path | None]:
        s = Path(self.script)
        s = s if s.is_absolute() else (base / s)
        if self.spec:
            sp = Path(self.spec)
            sp = sp if sp.is_absolute() else (base / sp)
        else:
            sp = s.with_suffix(".figtune.yaml")
        return s.resolve(), (sp.resolve() if sp.exists() else None)


@dataclass
class MontageSpec:
    version: str = "0.1"
    rows: int = 1
    cols: int = 2
    align: str = "axes"          # axes | bbox
    gap_pt: float = 14.0
    label_template: str = "({a})"
    auto_label: bool = True
    panels: list[PanelRef] = field(default_factory=list)

    def placements(self) -> list[tuple[int, int, int, int]]:
        """패널마다 (row, col, rowspan, colspan). 자리가 안 맞으면 알린다.

        자리를 적지 않은 패널은 남은 칸에 읽는 순서로 놓는다. 이미 차지된
        칸은 건너뛰므로, 넓은 패널 하나를 지정하고 나머지는 맡겨 두면 된다.

        겹침과 범위 이탈은 조용히 넘기지 않는다. GridSpec은 겹쳐도 그리기
        때문에, 알리지 않으면 패널 하나가 다른 패널에 덮여 사라진 채 나온다.
        """
        taken = [[False] * self.cols for _ in range(self.rows)]
        out: list[tuple[int, int, int, int] | None] = [None] * len(self.panels)

        def claim(i, r, c, rs, cs):
            if r < 0 or c < 0 or r + rs > self.rows or c + cs > self.cols:
                raise ValueError(_t(
                    "{script}의 자리가 격자를 벗어납니다: "
                    "({r},{c}) {rs}x{cs} / 격자 {rows}x{cols}",
                    script=self.panels[i].script, r=r, c=c, rs=rs, cs=cs,
                    rows=self.rows, cols=self.cols))
            for rr in range(r, r + rs):
                for cc in range(c, c + cs):
                    if taken[rr][cc]:
                        raise ValueError(_t(
                            "{script}의 자리가 다른 패널과 겹칩니다: ({r},{c})",
                            script=self.panels[i].script, r=rr, c=cc))
                    taken[rr][cc] = True
            out[i] = (r, c, rs, cs)

        for i, p in enumerate(self.panels):
            if p.row is not None and p.col is not None:
                claim(i, int(p.row), int(p.col),
                      max(1, int(p.rowspan)), max(1, int(p.colspan)))

        free = ((r, c) for r in range(self.rows) for c in range(self.cols))
        for i, p in enumerate(self.panels):
            if out[i] is not None:
                continue
            for r, c in free:
                if not taken[r][c]:
                    claim(i, r, c, 1, 1)
                    break
            else:
                raise ValueError(_t(
                    "격자 {rows}x{cols}에 패널 {n}개를 놓을 칸이 모자랍니다.",
                    rows=self.rows, cols=self.cols, n=len(self.panels)))
        return [o for o in out if o is not None]

    def to_dict(self) -> dict:
        return {"figtune_montage_version": self.version,
                "grid": {"rows": self.rows, "cols": self.cols},
                "align": self.align, "gap_pt": self.gap_pt,
                "label_template": self.label_template,
                "auto_label": self.auto_label,
                "panels": [asdict(p) for p in self.panels]}

    @classmethod
    def from_dict(cls, d: dict) -> "MontageSpec":
        g = d.get("grid") or {}
        return cls(version=d.get("figtune_montage_version", "0.1"),
                   rows=int(g.get("rows", 1)), cols=int(g.get("cols", 2)),
                   align=d.get("align", "axes"),
                   gap_pt=float(d.get("gap_pt", 14.0)),
                   label_template=d.get("label_template", "({a})"),
                   auto_label=bool(d.get("auto_label", True)),
                   panels=[PanelRef(**p) for p in (d.get("panels") or [])])

    def dump(self, path) -> None:
        Path(path).write_text(
            yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True),
            encoding="utf-8")

    @classmethod
    def load(cls, path) -> "MontageSpec":
        return cls.from_dict(
            yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})


def build(mspec: MontageSpec, base_dir: Path | str = ".",
          python: str | None = None) -> M.MontageResult:
    """스크립트들을 실행해 합성 결과를 만든다.

    두 번 렌더한다. 첫 번째는 각 패널의 axes 크기를 재기 위해서고,
    두 번째는 공통 크기로 다시 잡은 뒤 실제로 뽑기 위해서다. 배율로 맞추면
    글씨가 찌그러지므로 이 왕복이 필요하다.
    """
    import matplotlib
    matplotlib.use("Agg")
    from .session import Session

    base = Path(base_dir).resolve()
    sessions, sizes = [], []

    for ref in mspec.panels:
        script, spec_path = ref.resolve(base)
        s = Session(python=python)
        s.open(script, spec=Spec.load(spec_path) if spec_path else None)
        sessions.append((s, ref))
        sizes.append(M.axes_size_inches(s.fig, ref.axes_index))

    if mspec.align == "axes" and sizes:
        target = (min(w for w, _ in sizes), min(h for _, h in sizes))
        for (s, ref), _ in zip(sessions, sizes):
            M.fit_axes_size(s.fig, target[0], target[1], ref.axes_index)

    labels = (M.default_labels(len(sessions), mspec.label_template)
              if mspec.auto_label else [r.label for _, r in sessions])

    panels = []
    for (s, ref), label in zip(sessions, labels):
        buf = io.StringIO()
        from matplotlib.figure import Figure
        Figure.savefig(s.fig, buf, format="svg")
        panels.append(M.panel_from_figure(
            s.fig, buf.getvalue(), ref.axes_index,
            label=(ref.label or label)))

    return M.compose(panels, mspec.rows, mspec.cols,
                     align=mspec.align, gap_pt=mspec.gap_pt)


# --- 모드 B: 진짜 단일 Figure로 합치기 -------------------------------------
#
# 패널 스크립트가 ax를 받는 함수를 노출하면, SVG 합성이 아니라 진짜 subplot
# 격자로 합칠 수 있다. 결과는 평범한 matplotlib 스크립트이므로 figtune이
# 여느 스크립트처럼 열어 편집하고 *_style.py를 만들 수 있다.
#
# 모드 A(montage)와의 차이:
#   A — 원본 수정 불필요 / SVG 합성물 / 패널은 각자 편집 / figtune 의존
#   B — plot(ax) 노출 필요 / 진짜 Figure / 통째로 편집 / 순수 matplotlib

import ast

_PLOT_NAMES = ("plot", "draw", "make_plot", "plot_panel", "render")


def detect_plot_function(script: Path | str) -> str | None:
    """ax를 첫 인자로 받는 최상위 함수를 찾는다. 없으면 None."""
    try:
        tree = ast.parse(Path(script).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    cands = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        args = [a.arg for a in node.args.args]
        if not args:
            continue
        if args[0] in ("ax", "axes", "axis"):
            cands.append(node.name)
    for preferred in _PLOT_NAMES:
        if preferred in cands:
            return preferred
    return cands[0] if cands else None


_AXES_MAKERS = ("subplots", "subplot", "add_subplot", "add_axes", "axes")


def detect_projection(script: Path | str) -> str | None:
    """이 패널이 원하는 투영('3d', 'polar', …). 평범한 2D면 None.

    axes의 클래스는 만들 때 정해진다 — 3D는 Axes3D, polar는 PolarAxes다.
    병합 격자가 평범한 Axes를 넘기면 3D 패널은 거기에 그릴 수 없고, 이미
    만들어진 뒤에는 바꿀 방법이 없다. 그래서 미리 읽어 둔다.

    보통 `__main__` 블록에 적혀 있다 — 패널이 단독 실행될 때 자기 축을
    어떻게 만드는지가 곧 어떤 축을 원하는지다.
    """
    try:
        tree = ast.parse(Path(script).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", getattr(node.func, "id", None)) \
                not in _AXES_MAKERS:
            continue
        for kw in node.keywords:
            if kw.arg == "projection" and isinstance(kw.value, ast.Constant):
                return kw.value.value
            if kw.arg == "polar" and getattr(kw.value, "value", None) is True:
                return "polar"
            # subplots는 subplot_kw로 한 겹 감싸서 받는다
            if kw.arg == "subplot_kw" and isinstance(kw.value, ast.Dict):
                for k, v in zip(kw.value.keys, kw.value.values):
                    if (isinstance(k, ast.Constant) and k.value == "projection"
                            and isinstance(v, ast.Constant)):
                        return v.value
    return None


def panel_problem(script: Path | str) -> str | None:
    """이 스크립트를 합칠 수 없는 이유. 합칠 수 있으면 None.

    합칠 수 없다는 것을 칸을 다 채우고 나서 알면 늦다. 고르는 자리에서
    미리 보여줄 수 있도록, 만들기 전에 같은 검사를 한 번 한다.
    """
    path = Path(script)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return _t("읽지 못했습니다: {err}", err=exc)

    fn = detect_plot_function(path)
    if fn is None:
        return _t("ax를 받는 plot(ax) 함수가 없습니다")
    try:
        inline.inline_panel(source, fn, "_probe", label=path.name)
    except inline.InlineError as exc:
        return str(exc)
    return None


MERGE_TEMPLATE = '''"""Generated by figtune — panel merge script

Self-contained: each panel's code was copied into this file, so it draws the
figure on its own. The panel scripts are no longer needed, and moving or
renaming them does not affect this file. The flip side is that later edits to
a panel script do not show up here — merge again to pick them up.

The result is an ordinary matplotlib Figure, so figtune can open and edit it
as a whole, and this file runs without figtune.

CELLS gives each panel its place as (row, col, rowspan, colspan), so a panel
may span several grid cells.
"""

import matplotlib.pyplot as plt

# (row, col, rowspan, colspan) — same order as the panel functions below
CELLS = {cells!r}

# Each panel's projection, or None for an ordinary 2D axes. An axes' class is
# fixed when it is created (Axes3D, PolarAxes, …), so a 3D panel needs the
# right kind of axes from the start — it cannot be converted afterwards.
PROJECTIONS = {projections!r}

PANEL_LABELS = {labels!r}


{panels}

PANELS = [{names}]

fig = plt.figure(figsize=({w!r}, {h!r}))
_gs = fig.add_gridspec({rows}, {cols})
_axes = [fig.add_subplot(_gs[_r:_r + _rs, _c:_c + _cs],
                         **({{}} if _p is None else {{"projection": _p}}))
         for (_r, _c, _rs, _cs), _p in zip(CELLS, PROJECTIONS)]

for _draw, _ax in zip(PANELS, _axes):
    _draw(_ax)

for _ax, _label in zip(_axes, PANEL_LABELS):
    # Axes3D.text takes (x, y, z, s); text2D is the 2D-in-axes-coords one.
    _put = getattr(_ax, "text2D", None) or _ax.text
    _put(-0.15, 1.02, _label, transform=_ax.transAxes,
         fontweight="bold", fontsize=11, va="bottom", ha="left")

fig.tight_layout()
'''


def generate_subplot_script(mspec: MontageSpec, out_path: Path | str,
                            base_dir: Path | str = ".",
                            panel_size: tuple = (4.0, 3.0)) -> Path:
    """모드 B 병합 스크립트를 만든다.

    각 패널의 코드를 이 파일 안으로 옮겨 담는다. 원본을 참조하면 파일을
    옮기거나 이름을 바꾸는 순간 깨지고, 논문에 딸려 보낼 때 폴더째 보내야
    한다. 대신 나중에 패널을 고쳐도 병합 결과에는 반영되지 않는다 —
    다시 병합해야 한다.

    패널 스크립트 중 하나라도 plot(ax)를 노출하지 않으면 무엇이 빠졌는지
    알리고 중단한다. 조용히 모드 A로 떨어지면 사용자가 어느 쪽 산출물을
    보고 있는지 알 수 없게 된다.
    """
    base = Path(base_dir).resolve()
    out = Path(out_path)
    blocks, names, projections, missing = [], [], [], []

    for i, ref in enumerate(mspec.panels):
        script, _ = ref.resolve(base)
        fn = detect_plot_function(script)
        if fn is None:
            missing.append(str(script))
            continue
        name = f"_panel_{i}"
        blocks.append(inline.inline_panel(
            script.read_text(encoding="utf-8"), fn, name, label=script.name))
        names.append(name)
        # 투영은 패널이 자기 축을 어떻게 만드는지에서 읽는다
        projections.append(detect_projection(script))

    if missing:
        raise ValueError(_t(
            "다음 스크립트에 ax를 받는 함수가 없습니다:\n  {scripts}\n\n"
            "각 스크립트에 다음 형태를 추가하세요:\n"
            "    def plot(ax):\n        ...\n"
            "    if __name__ == '__main__':\n"
            "        fig, ax = plt.subplots(); plot(ax)\n"
            "그러면 단독 실행도 그대로 되고 병합도 가능해집니다.",
            scripts="\n  ".join(missing)))

    labels = M.default_labels(len(names), mspec.label_template)
    out.write_text(MERGE_TEMPLATE.format(
        panels="\n\n".join(blocks), names=", ".join(names),
        cells=mspec.placements(), projections=projections,
        labels=labels,
        rows=mspec.rows, cols=mspec.cols,
        w=round(panel_size[0] * mspec.cols, 2),
        h=round(panel_size[1] * mspec.rows, 2)), encoding="utf-8")
    return out


def can_use_subplot_mode(mspec: MontageSpec, base_dir: Path | str = ".") -> dict:
    """패널별로 모드 B가 가능한지 조사한다."""
    base = Path(base_dir).resolve()
    out = {}
    for ref in mspec.panels:
        script, _ = ref.resolve(base)
        out[str(script)] = detect_plot_function(script)
    return out
