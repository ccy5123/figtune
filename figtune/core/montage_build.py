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

from . import montage as M
from .spec import Spec


@dataclass
class PanelRef:
    script: str
    spec: str = ""              # .figtune.yaml 경로. 비우면 스크립트 옆 기본값
    axes_index: int = 0         # 어느 axes를 정렬 기준으로 삼을지
    label: str = ""

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


MERGE_TEMPLATE = '''"""figtune 생성 — 패널 병합 스크립트

각 패널 스크립트의 plot(ax) 함수를 subplot 격자에 그린다. 결과는 평범한
matplotlib Figure이므로 figtune으로 열어 통째로 편집할 수 있고, 이 파일
자체는 figtune 없이도 실행된다.

패널을 추가·교체하려면 아래 PANELS만 고치면 된다.
"""

import runpy

import matplotlib.pyplot as plt

# (스크립트 경로, 함수 이름)
PANELS = {panels!r}

PANEL_LABELS = {labels!r}

fig, axes = plt.subplots({rows}, {cols}, figsize=({w!r}, {h!r}))
_axes = list(axes.ravel()) if hasattr(axes, "ravel") else [axes]

for (_path, _fn), _ax in zip(PANELS, _axes):
    runpy.run_path(_path)[_fn](_ax)

for _ax in _axes[len(PANELS):]:          # 남는 칸은 비운다
    _ax.set_visible(False)

for _ax, _label in zip(_axes, PANEL_LABELS):
    _ax.text(-0.15, 1.02, _label, transform=_ax.transAxes,
             fontweight="bold", fontsize=11, va="bottom", ha="left")

fig.tight_layout()
'''


def generate_subplot_script(mspec: MontageSpec, out_path: Path | str,
                            base_dir: Path | str = ".",
                            panel_size: tuple = (4.0, 3.0)) -> Path:
    """모드 B 병합 스크립트를 만든다.

    패널 스크립트 중 하나라도 plot(ax)를 노출하지 않으면 무엇이 빠졌는지
    알리고 중단한다. 조용히 모드 A로 떨어지면 사용자가 어느 쪽 산출물을
    보고 있는지 알 수 없게 된다.
    """
    base = Path(base_dir).resolve()
    out = Path(out_path)
    entries, missing = [], []

    for ref in mspec.panels:
        script, _ = ref.resolve(base)
        fn = detect_plot_function(script)
        if fn is None:
            missing.append(str(script))
            continue
        try:
            rel = os.path.relpath(script, out.parent)
        except ValueError:
            rel = str(script)
        entries.append((rel, fn))

    if missing:
        raise ValueError(
            "다음 스크립트에 ax를 받는 함수가 없습니다:\n  "
            + "\n  ".join(missing)
            + "\n\n각 스크립트에 다음 형태를 추가하세요:\n"
            "    def plot(ax):\n        ...\n"
            "    if __name__ == '__main__':\n"
            "        fig, ax = plt.subplots(); plot(ax)\n"
            "그러면 단독 실행도 그대로 되고 병합도 가능해집니다.")

    labels = M.default_labels(len(entries), mspec.label_template)
    out.write_text(MERGE_TEMPLATE.format(
        panels=entries, labels=labels, rows=mspec.rows, cols=mspec.cols,
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
