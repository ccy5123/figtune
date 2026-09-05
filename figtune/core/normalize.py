"""스크립트 정규형.

── 정규형의 정의 ────────────────────────────────────────────────────
    <imports 및 데이터 준비>          모듈 수준

    def plot(ax):                     그리기는 전부 여기
        ...

    if __name__ == "__main__":        단독 실행 진입점
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=...)
        plot(ax)

이 형태를 만족하면:
  · 단독 실행이 그대로 된다
  · `figtune merge`로 진짜 단일 Figure에 합쳐진다 (모드 B)
  · figtune이 여느 스크립트처럼 열어 편집한다
─────────────────────────────────────────────────────────────────────

── 기계적으로 처리할 수 있는 범위 ──────────────────────────────────
임의의 Python을 정규형으로 바꾸는 것은 일반적으로 불가능하다. 그래서
**인식 가능한 부분집합에서만** 동작하고, 벗어나면 무엇이 걸렸는지 정확히
알리고 멈춘다. 추측해서 고치지 않는다 — 사용자의 그림이 조용히 달라지는
것이 가장 나쁜 결과다.

인식하는 형태:
  · 모듈 수준에 `fig, ax = plt.subplots(...)`가 정확히 한 번
  · 그 뒤 문장은 ax(또는 fig의 허용된 메서드)만 건드린다
거부하는 형태:
  · subplots가 여러 축을 만드는 경우 (axes 배열)
  · fig에 허용되지 않은 조작 (savefig/tight_layout 외)
  · 그리기 문장이 조건문·반복문 안에 있는 경우
─────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# plot(ax) 안으로 옮길 때 버려도 되는 figure 수준 호출.
# 병합 스크립트가 대신 처리하거나, 단독 실행 블록으로 옮긴다.
_FIG_DROPPABLE = {"tight_layout", "savefig", "show", "set_size_inches",
                  "subplots_adjust", "align_labels", "canvas"}

_PLT_DROPPABLE = {"show", "savefig", "tight_layout"}

# figure 호출 중 `ax.figure.xxx(...)`로 바꿔 함수 안으로 옮겨도 되는 것.
# colorbar는 인자로 받은 축에 붙으므로 병합 격자에서도 제자리를 지킨다.
# suptitle은 figure 전체의 것이라 넣지 않는다 — 병합하면 패널마다 서로
# 덮어써서 마지막 것만 남는다.
_FIG_REWRITE = {"colorbar"}


def _bound_names(node) -> set[str]:
    """이 문장이 새로 묶는 이름들."""
    out = set()
    for t in getattr(node, "targets", []):
        if isinstance(t, ast.Name):
            out.add(t.id)
        elif isinstance(t, ast.Tuple):
            out |= {e.id for e in t.elts if isinstance(e, ast.Name)}
    return out


def _classify(node, targets: set[str], fig_name: str) -> str:
    """문장을 head / body / drop / rewrite / refuse 로 가른다.

    targets는 '그리기 대상'의 이름 집합이다. ax에서 시작해 본문으로 옮겨진
    문장이 묶은 이름까지 자라난다. `ax2 = ax.twinx()` 다음 줄의
    `ax2.plot(...)`은 ax를 직접 쓰지 않지만 그리기 문장이기 때문이다.
    """
    used = _names_used(node)
    touches = bool(targets & used) or fig_name in used

    if not touches:
        attr = _plt_call(node)
        if attr in _PLT_DROPPABLE:
            return "drop"
        if attr is not None and "plt" in used:
            return "refuse-plt"
        return "head"

    # fig를 쓰는 문장은 무조건 먼저 판정한다. 함수 안에는 fig가 없으므로
    # 그대로 옮기면 NameError가 난다.
    if fig_name in used:
        v = _fig_verdict(node, fig_name)
        if v is not None:
            return v
        return "refuse-fig"

    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        return "body" if _calls_on(node, targets) else "refuse-leak"

    # 단순 대입은 옮겨도 안전하다. `im = ax.imshow(...)`,
    # `ax2 = ax.twinx()` 같은 형태가 여기 걸린다.
    if isinstance(node, ast.Assign) and _bound_names(node):
        return "body" if _calls_on(node, targets) else "refuse-leak"

    return "refuse-stmt"


def _calls_on(node, targets: set[str]) -> bool:
    """그리기 대상의 메서드를 부르는 문장인가.

    판단 기준은 **바깥쪽 호출**이다. `ax.plot(...)`이나 `cb.set_label(...)`은
    그리기지만, `print(im.get_array().max())`는 안쪽에 대상 호출이 있어도
    문장 자체는 출력이다. 옮기면 실행 시점이 import에서 plot() 호출로
    바뀐다 — 조용한 동작 변경이라 막는다.
    """
    expr = node.value if isinstance(node, (ast.Expr, ast.Assign)) else None
    if not isinstance(expr, ast.Call):
        return False
    f = expr.func
    return isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
        and f.value.id in targets


def _fig_verdict(node, fig_name: str) -> str | None:
    """fig를 쓰는 문장의 판정. 모르면 None."""
    call = None
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        call = node.value
    elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
        call = node.value
    if call is None:
        return None
    f = call.func
    attr = getattr(f, "attr", None)
    base = getattr(getattr(f, "value", None), "id", None)
    if base != fig_name:
        return None
    if attr in _FIG_DROPPABLE:
        return "drop"
    if attr in _FIG_REWRITE:
        return "rewrite"
    return None


def _partition(tail, ax_name: str, fig_name: str):
    """문장들을 순서대로 훑으며 판정한다. 그리기 대상 집합이 자라난다.

    반환: [(node, verdict)], 본문에서 묶인 이름 집합
    """
    targets = {ax_name}
    out, bound = [], set()
    for node in tail:
        verdict = _classify(node, targets, fig_name)
        if verdict in ("body", "rewrite"):
            names = _bound_names(node)
            targets |= names
            bound |= names
        out.append((node, verdict))
    return out, bound


@dataclass
class Report:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    ax_name: str = "ax"
    fig_name: str = "fig"
    figsize: str = "None"
    n_plot_stmts: int = 0

    def explain(self) -> str:
        if self.ok:
            return "정규형으로 바꿀 수 있습니다."
        return "정규형으로 바꿀 수 없습니다:\n  " + "\n  ".join(self.reasons)


def _is_subplots(node) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subplots")


def _single_axes(call: ast.Call) -> bool:
    """subplots가 단일 축을 만드는가."""
    pos = [a for a in call.args if isinstance(a, ast.Constant)]
    if len(pos) >= 2 and (pos[0].value != 1 or pos[1].value != 1):
        return False
    for kw in call.keywords:
        if kw.arg in ("nrows", "ncols") and isinstance(kw.value, ast.Constant):
            if kw.value.value != 1:
                return False
    return True


def _figsize_src(call: ast.Call, src: str) -> str:
    for kw in call.keywords:
        if kw.arg == "figsize":
            return ast.get_source_segment(src, kw.value) or "None"
    return "None"


def _plt_call(node) -> str | None:
    """모듈 수준의 `plt.xxx(...)` 호출이면 그 이름을 돌려준다."""
    if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
        return None
    f = node.value.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f.attr
    return None


def _names_used(node) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def analyze(source: str) -> Report:
    """정규형으로 바꿀 수 있는지 조사한다. 파일을 건드리지 않는다."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return Report(False, [f"구문 오류: {exc}"])

    # 이미 정규형인가
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            args = [a.arg for a in node.args.args]
            if args and args[0] in ("ax", "axes", "axis"):
                return Report(True, ["이미 정규형입니다."], n_plot_stmts=0)

    subplots = [(i, n) for i, n in enumerate(tree.body)
                if isinstance(n, ast.Assign) and _is_subplots(n.value)]
    if len(subplots) != 1:
        return Report(False, [
            f"모듈 수준 plt.subplots() 호출이 {len(subplots)}개입니다. "
            "정확히 하나여야 합니다."])

    idx, assign = subplots[0]
    call = assign.value
    if not _single_axes(call):
        return Report(False, [
            "subplots()가 여러 축을 만듭니다. 이미 다패널 figure이므로 "
            "병합 대상이 아닙니다."])

    tgt = assign.targets[0]
    if not (isinstance(tgt, ast.Tuple) and len(tgt.elts) == 2
            and all(isinstance(e, ast.Name) for e in tgt.elts)):
        return Report(False, ["`fig, ax = plt.subplots(...)` 형태가 아닙니다."])
    fig_name, ax_name = tgt.elts[0].id, tgt.elts[1].id

    reasons, n_stmts = [], 0
    tail = tree.body[idx + 1:]
    verdicts, bound = _partition(tail, ax_name, fig_name)

    for node, verdict in verdicts:
        if verdict in ("body", "rewrite"):
            n_stmts += 1
        elif verdict == "refuse-plt":
            attr = _plt_call(node)
            reasons.append(
                f"{node.lineno}행: pyplot 상태 호출 plt.{attr}()은 어느 축을 "
                f"가리키는지 알 수 없습니다. ax.{attr}(...) 형태로 바꾸세요.")
        elif verdict == "refuse-fig":
            attr = getattr(getattr(getattr(node, "value", None), "func", None),
                           "attr", None)
            reasons.append(
                f"{node.lineno}행: figure 수준 호출 {attr!r}은 옮길 수 "
                "없습니다. 손으로 처리하세요.")
        elif verdict == "refuse-stmt":
            reasons.append(
                f"{node.lineno}행: 그리기 대상을 쓰는 문장이 단순 호출이나 "
                "대입이 아닙니다 (조건문·반복문은 자동 변환하지 않습니다).")
        elif verdict == "refuse-leak":
            reasons.append(
                f"{node.lineno}행: 그리기 대상을 그리기 외 용도로 씁니다"
                "(출력·계산 등). 함수 안으로 옮기면 실행 시점이 달라지므로 "
                "손으로 처리하세요.")

    # 함수 안으로 옮긴 이름을 모듈 수준에서 쓰면 NameError가 난다.
    # 옮기고 나서 터지는 것보다 옮기기 전에 막는 편이 낫다.
    for node, verdict in verdicts:
        if verdict != "head":
            continue
        leaked = bound & _names_used(node)
        if leaked:
            reasons.append(
                f"{node.lineno}행: {', '.join(sorted(leaked))}은(는) plot(ax) "
                "안으로 옮겨지는데 이 문장이 모듈 수준에서 씁니다.")

    if n_stmts == 0 and not reasons:
        reasons.append("그리기 문장을 찾지 못했습니다.")

    return Report(not reasons, reasons or ["변환 가능합니다."],
                  ax_name=ax_name, fig_name=fig_name,
                  figsize=_figsize_src(call, source), n_plot_stmts=n_stmts)


TEMPLATE = '''{head}

def plot(ax):
{body}

if __name__ == "__main__":
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize={figsize})
    plot(ax)
    plt.show()
'''


def normalize(source: str) -> tuple[str, Report]:
    """정규형 소스를 만든다. 원본 문자열은 건드리지 않는다.

    변환할 수 없으면 (원본, 실패 리포트)를 그대로 돌려준다.
    """
    rep = analyze(source)
    if not rep.ok:
        return source, rep
    if rep.n_plot_stmts == 0:
        return source, rep                # 이미 정규형

    tree = ast.parse(source)
    idx = next(i for i, n in enumerate(tree.body)
               if isinstance(n, ast.Assign) and _is_subplots(n.value))

    head_nodes, body_chunks = list(tree.body[:idx]), []
    verdicts, _ = _partition(tree.body[idx + 1:], rep.ax_name, rep.fig_name)
    for node, verdict in verdicts:
        if verdict == "drop":
            continue                      # 단독 실행 블록이 대신 처리한다
        if verdict == "body":
            body_chunks.append(ast.get_source_segment(source, node) or "")
        elif verdict == "rewrite":
            seg_ = ast.get_source_segment(source, node) or ""
            body_chunks.append(
                seg_.replace(f"{rep.fig_name}.", "ax.figure.", 1))
        else:
            head_nodes.append(node)

    def seg(nodes):
        return [ast.get_source_segment(source, n) or "" for n in nodes]

    head = "\n".join(seg(head_nodes)).rstrip()
    body_lines = []
    for chunk in body_chunks:
        for line in chunk.splitlines():
            body_lines.append("    " + line if line.strip() else "")
    body = "\n".join(body_lines) or "    pass"

    # 함수 인자 이름은 항상 ax로 고정한다 (정규형의 일부)
    if rep.ax_name != "ax":
        body = _rename(body, rep.ax_name, "ax")

    out = TEMPLATE.format(head=head, body=body, figsize=rep.figsize)
    ast.parse(out)                        # 생성물이 문법적으로 유효한지 확인
    return out, rep


def _rename(body: str, old: str, new: str) -> str:
    """식별자만 안전하게 바꾼다. 문자열 안의 같은 글자는 건드리지 않는다."""
    import re
    return re.sub(rf"\b{re.escape(old)}\b", new, body)


def normalize_file(path: Path | str, out_path: Path | str | None = None,
                   in_place: bool = False) -> tuple[Path | None, Report]:
    """파일을 정규형으로 바꾼다.

    in_place=False가 기본이다. 사용자의 원본을 덮어쓰는 것은 명시적 지시가
    있을 때만 한다.
    """
    p = Path(path)
    src = p.read_text(encoding="utf-8")
    out, rep = normalize(src)
    if not rep.ok:
        return None, rep
    if rep.n_plot_stmts == 0:
        return p, rep                     # 이미 정규형이면 그대로
    dst = Path(out_path) if out_path else (p if in_place else
                                           p.with_name(p.stem + "_norm.py"))
    dst.write_text(out, encoding="utf-8")
    return dst, rep
