"""spec → 살아있는 Figure.

적용 순서가 중요하다. 범례는 handle/label이 확정된 뒤에 마지막으로 만들어야
하고, 레이아웃 엔진은 수동 위치 조정과 충돌하므로 별도 취급한다.
"""

from __future__ import annotations

from . import props as P
from . import selector as sel
from .spec import Spec, UserText

# 적용 순서와 정규 정렬 순서는 같은 표를 쓴다. 둘이 어긋나면 "저장한 대로
# 다시 적용된다"는 보장이 깨진다.
from .canon import KIND_ORDER as _ORDER


class ApplyReport:
    def __init__(self):
        self.failed: list[tuple[str, str, str]] = []   # (path, prop, 사유)

    def fail(self, path, prop, why):
        self.failed.append((path, prop, str(why)))

    def __bool__(self):
        return not self.failed


def transform_for(ax, coords: str):
    if coords == "data":
        return ax.transData
    if coords == "figure":
        return ax.figure.transFigure
    return ax.transAxes


def ensure_text(fig, t: UserText):
    """user text artist를 만들거나 찾아서 최신 상태로 만든다."""
    try:
        ax = fig.axes[t.axes]
    except IndexError:
        return None
    art = None
    for cand in ax.texts:
        if getattr(cand, "_figtune_id", None) == t.id:
            art = cand
            break
    if art is None:
        art = ax.text(t.position[0], t.position[1], t.text,
                      transform=transform_for(ax, t.coords))
        art._figtune_id = t.id
    else:
        art.set_text(t.text)
        art.set_position((t.position[0], t.position[1]))
        art.set_transform(transform_for(ax, t.coords))
    for k, v in t.style().items():
        try:
            getattr(art, f"set_{k}")(v)
        except Exception:
            pass
    return art


def apply_spec(fig, spec: Spec, report: ApplyReport | None = None) -> ApplyReport:
    report = report or ApplyReport()

    # user text를 먼저 만들어야 그에 대한 override를 걸 수 있다
    for t in spec.texts:
        try:
            ensure_text(fig, t)
        except Exception as exc:
            report.fail(sel.usertext(t.axes, t.id), "-", exc)

    def rank(path: str) -> int:
        try:
            return _ORDER.get(sel.parse(path).kind, 8)
        except sel.SelectorError:
            return 8

    for path in sorted(spec.overrides, key=rank):
        over = spec.overrides[path]
        try:
            kind = sel.parse(path).kind
        except sel.SelectorError as exc:
            report.fail(path, "-", exc)
            continue

        if kind == "figlegend":
            try:
                P.apply_fig_legend(fig, over)
            except Exception as exc:
                report.fail(path, "figlegend", exc)
            continue

        if kind == "legend":
            try:
                P.apply_legend(fig.axes[sel.parse(path).axes], over)
            except Exception as exc:
                report.fail(path, "legend", exc)
            continue

        view_keys = {"elev", "azim", "roll", "dist_zoom"}
        if kind == "axes" and view_keys & set(over):
            try:
                P.apply_view(fig.axes[sel.parse(path).axes], over)
            except Exception as exc:
                report.fail(path, "view", exc)

        for name, value in over.items():
            if kind == "axes" and name in view_keys:
                continue
            try:
                P.apply(fig, path, name, value)
            except Exception as exc:
                report.fail(path, name, exc)

    return report


def apply_one(fig, spec: Spec, path: str, name: str, value) -> None:
    """GUI 편집 한 건을 spec과 figure에 동시에 반영한다."""
    spec.set(path, name, value)
    if sel.parse(path).kind == "legend":
        P.apply_legend(fig.axes[sel.parse(path).axes], spec.of(path))
    else:
        P.apply(fig, path, name, value)


def sync_text(fig, spec: Spec, tid: str) -> None:
    t = spec.text_by_id(tid)
    if t is not None:
        ensure_text(fig, t)


def remove_text(fig, spec: Spec, tid: str) -> None:
    t = spec.text_by_id(tid)
    if t is None:
        return
    try:
        ax = fig.axes[t.axes]
        for cand in list(ax.texts):
            if getattr(cand, "_figtune_id", None) == tid:
                cand.remove()
    except IndexError:
        pass
    spec.remove_text(tid)
