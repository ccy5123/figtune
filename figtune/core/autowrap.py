"""plot(ax) 없는 스크립트를 합칠 수 있는 형태로 감싼다.

matplotlib은 figure 사이의 axes 이동을 지원하지 않는다. 그래서 여러 그림을
하나의 진짜 Figure로 합치려면, 패널 내용을 우리가 만든 axes에 다시 그리는
수밖에 없다. `plot(ax)`가 그것을 가능하게 하는 계약이고, 이 모듈은 그 계약이
없는 스크립트에 그것을 씌운다.

방법은 하나뿐이다 — **자기 figure를 만드는 줄을 걷어내고, 이미 있는 이름이
넘겨받은 axes를 가리키게 한다.** 본문은 손대지 않는다. 어느 문장이 어느 축을
건드리는지 좇기 시작하면 틀리기 시작하고, 틀렸다는 것이 그림에서만 드러난다.

figtune은 원본을 고치지 않는다. 감싸기는 병합 파일을 만들 때만 일어난다.
"""

from __future__ import annotations

import ast

from ..i18n import t as _t


class WrapError(ValueError):
    """감쌀 수 없는 스크립트."""


# 축을 만드는 호출들. 여기 없는 방법으로 만들면 감지하지 못한다.
_MAKERS = ("subplots", "subplot", "add_subplot", "add_axes", "axes", "gca")
_FIG_MAKERS = ("figure",)
# 병합 파일 안에서는 뜻이 없거나 해로운 호출들
_DROP = ("show", "savefig", "close")


def _call_name(node) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    return getattr(node.func, "attr", getattr(node.func, "id", None))


def _subplots_count(node) -> int:
    """plt.subplots(...)가 만드는 축의 개수."""
    nums = [a.value for a in node.args if isinstance(a, ast.Constant)]
    kw = {k.arg: k.value for k in node.keywords}
    for name in ("nrows", "ncols"):
        v = kw.get(name)
        if isinstance(v, ast.Constant):
            nums.append(v.value)
    total = 1
    for n in nums:
        if isinstance(n, int):
            total *= n
    return max(1, total)


def _subplots_shape(node) -> tuple[int, int]:
    """plt.subplots(...)가 만드는 격자 모양 (행, 열)."""
    kw = {k.arg: k.value for k in node.keywords}
    pos = [a.value for a in node.args if isinstance(a, ast.Constant)]

    def pick(i, name):
        v = kw.get(name)
        if isinstance(v, ast.Constant) and isinstance(v.value, int):
            return v.value
        return pos[i] if len(pos) > i and isinstance(pos[i], int) else 1

    return max(1, pick(0, "nrows")), max(1, pick(1, "ncols"))


def axes_shape(source: str) -> tuple[int, int]:
    """이 스크립트가 만드는 축 격자의 모양. 못 읽으면 (1, 1).

    영역을 이 모양으로 다시 나눠 그 축들을 건네면, 2패널 스크립트가 두 칸을
    차지하면서도 본문을 그대로 쓸 수 있다.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return (1, 1)
    for node in ast.walk(tree):
        if _call_name(node) == "subplots":
            return _subplots_shape(node)
    return (1, 1)


def axes_count(source: str) -> int:
    """이 스크립트가 만드는 축의 개수. 하나도 안 만들면 1(gca)로 본다.

    상태 기반 스크립트(plt.plot만 쓰는 것)도 결국 축 하나를 쓴다.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise WrapError(_t("해석하지 못했습니다: {err}", err=exc)) from exc

    total = 0
    for node in ast.walk(tree):
        name = _call_name(node)
        if name == "subplots":
            total += _subplots_count(node)
        elif name in ("subplot", "add_subplot", "add_axes"):
            total += 1
    return total or 1


def _defines_plot(tree) -> bool:
    from .montage_build import _PLOT_NAMES

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            if args and args[0] in ("ax", "axes", "axis"):
                return True
            if node.name in _PLOT_NAMES:
                return True
    return False


def _axes_name(tree) -> str | None:
    """축을 받는 이름. `fig, ax = plt.subplots()`의 ax, 또는 add_subplot의 좌변."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        name = _call_name(node.value)
        target = node.targets[0]
        if name == "subplots" and isinstance(target, ast.Tuple) \
                and len(target.elts) == 2 and isinstance(target.elts[1], ast.Name):
            return target.elts[1].id
        if name in ("add_subplot", "subplot", "add_axes", "gca") \
                and isinstance(target, ast.Name):
            return target.id
    return None


def _drop_lines(tree) -> set[int]:
    """걷어낼 줄 번호.

    자기 figure를 만드는 문장과 show/savefig/close. 남겨 두면 병합 격자가
    아니라 딴 데 그려지거나, 병합 파일을 돌릴 때 창이 뜨고 파일이 생긴다.
    """
    drop: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.Expr)):
            continue
        calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
        names = {_call_name(c) for c in calls}
        if names & set(_MAKERS) | names & set(_FIG_MAKERS) or names & set(_DROP):
            drop.update(range(node.lineno,
                              (node.end_lineno or node.lineno) + 1))
    return drop


def wrap_source(source: str, func: str = "plot",
                allow_multi: bool = False) -> str:
    """스크립트를 `def plot(ax):` 하나로 감싼다.

    축을 여러 개 만드는 스크립트는 기본적으로 거부한다. allow_multi를 켜면
    `def plot(axs):` 형태로 감싸고, 축을 받던 이름이 넘겨받은 **목록**을
    가리키게 한다 — 부르는 쪽이 그만큼의 칸을 준비했을 때만 쓴다.

    돌려주는 것은 함수 정의 문자열이다. inline_panel과 달리 호출은 붙이지
    않는다 — 감싼 것 자체가 그 함수이기 때문이다.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise WrapError(_t("해석하지 못했습니다: {err}", err=exc)) from exc

    if _defines_plot(tree):
        raise WrapError(_t("이미 ax를 받는 함수가 있습니다 — 감쌀 필요가 없습니다."))

    n = axes_count(source)
    multi = n > 1
    if multi and not allow_multi:
        raise WrapError(_t(
            "축을 {n}개 만드는 스크립트입니다. 한 칸에 진짜 축으로 넣을 수 "
            "없습니다 — 칸 {n}개를 차지하게 하거나, 패널마다 파일을 나누세요.",
            n=n))

    drop = _drop_lines(tree)
    kept = [ln for i, ln in enumerate(source.splitlines(), start=1)
            if i not in drop]
    while kept and not kept[0].strip():
        kept.pop(0)
    while kept and not kept[-1].strip():
        kept.pop()

    body = "\n".join(("    " + ln) if ln.strip() else "" for ln in kept)

    # 축을 받던 이름이 넘겨받은 축을 가리키게 한다. 이름이 없으면(상태 기반)
    # pyplot의 현재 축을 그것으로 돌려 plt.plot(...)이 여기에 그리게 한다.
    name = _axes_name(tree)
    # 생성되는 코드는 영어다. 사용자 언어에 따라 파일 바이트가 달라지면
    # 정규형의 결정성이 깨지고 사람마다 다른 diff가 나온다.
    if multi:
        # 축을 받던 이름이 넘겨받은 목록을 가리키게 한다. axes[0]·axes[1]이
        # 우리가 만든 축이 된다.
        head = [f"def {func}(axs):", "    fig = axs[0].figure"]
        if name and name != "axs":
            head.append(f"    {name} = axs")
    else:
        # _plt는 자기 이름으로 가져온다. 본문에도 `import ... as plt`가 있으면
        # 그 이름은 함수의 지역이 되어, 그 줄보다 먼저 쓰면 UnboundLocalError다.
        head = [f"def {func}(ax):",
                "    import matplotlib.pyplot as _plt",
                "    _plt.sca(ax)         "
                "# so bare plt.plot(...) draws here too",
                # 본문이 fig를 쓰는 경우가 흔하다 (tight_layout, suptitle …)
                "    fig = ax.figure"]
        if name and name != "ax":
            head.append(f"    {name} = ax")
    return "\n".join(head) + "\n" + body + "\n"
