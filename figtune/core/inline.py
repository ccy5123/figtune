"""패널 스크립트를 병합 파일 안으로 펼쳐 넣는다.

병합 결과는 그 파일 하나로 그림이 그려져야 한다. 원본을 참조하면 파일을
옮기거나 이름을 바꾸는 순간 깨지고, 논문에 딸려 보낼 때 폴더째 보내야 한다.

패널 하나를 함수 하나로 감싼다. 모듈 수준에 있던 상수·데이터·헬퍼가 전부
함수의 지역 이름이 되므로, 모든 패널이 plot()이라는 같은 이름을 써도 서로
가리지 않는다. 이름 바꾸기나 접두사 붙이기로 푸는 것보다 안전하다 — 문자열
안의 이름이나 getattr까지 좇을 필요가 없다.

원문을 재조립하지 않고 줄 단위로 옮긴다. 병합 파일은 사람이 이어서 고칠
코드이므로 주석과 서식이 남아야 한다.

Qt도 matplotlib도 import하지 않는다 — 순수한 소스 변환이다.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path, PurePosixPath

from ..i18n import t as _t


class InlineError(ValueError):
    """펼쳐 넣을 수 없는 스크립트."""


def _main_guard(node) -> bool:
    """`if __name__ == "__main__":` 인가.

    남겨 두면 병합 스크립트를 직접 돌릴 때 패널이 자기 figure를 하나 더
    만든다. 화면에는 빈 창이, 파일에는 엉뚱한 그림이 남는다.
    """
    if not isinstance(node, ast.If):
        return False
    t = node.test
    return (isinstance(t, ast.Compare)
            and isinstance(t.left, ast.Name) and t.left.id == "__name__"
            and len(t.comparators) == 1
            and isinstance(t.comparators[0], ast.Constant)
            and t.comparators[0].value == "__main__")


def _future_import(node) -> bool:
    """from __future__ import … 인가.

    모듈 맨 위에만 올 수 있어서 함수 안에 넣으면 SyntaxError다. 병합 파일은
    자기 것을 이미 갖고 있으므로 여기서는 버린다.
    """
    return isinstance(node, ast.ImportFrom) and node.module == "__future__"


def _uses_file(tree) -> bool:
    """__file__을 쓰는가.

    함수 안으로 옮기면 __file__이 병합 파일의 것이 된다. 데이터 경로를
    그것으로 잡은 스크립트는 조용히 엉뚱한 파일을 읽게 되므로 막는다.
    """
    return any(isinstance(n, ast.Name) and n.id == "__file__"
               for n in ast.walk(tree))


def _defines(tree, name: str) -> bool:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == name:
            return True
    return False


# 데이터를 읽는 흔한 호출들. 여기 없는 방법으로 읽으면 고치지 못한다.
_READERS = (
    "read_csv", "read_excel", "read_table", "read_parquet", "read_json",
    "read_pickle", "read_hdf", "loadtxt", "genfromtxt", "load", "open",
    "imread", "read_feather", "read_stata",
)


def _rewrites(tree, from_dir: Path, to_dir: Path) -> dict:
    """고쳐야 할 경로 리터럴: (줄, 열) -> (원문 길이, 새 경로).

    패널의 상대 경로는 그 패널 폴더 기준이다. 병합 파일 안으로 옮기면 병합
    파일 폴더에서 풀리므로, 병합 파일에서 보이는 경로로 바꿔 옮긴다.

    절대 경로로 바꾸지 않는다. 이 PC에서는 편하지만 다른 사람에게 보내는
    순간 깨지고, 논문 그림에서는 그쪽이 더 아프다.
    """
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", getattr(node.func, "id", None)) \
                not in _READERS:
            continue
        for arg in node.args[:1]:
            if not (isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)):
                continue          # 변수로 조립한 경로는 알 수 없다
            if PurePosixPath(arg.value).is_absolute() \
                    or Path(arg.value).is_absolute():
                continue          # 절대 경로는 어디서든 같다
            new = os.path.relpath(from_dir / arg.value, to_dir)
            if new != arg.value:
                out[(arg.lineno, arg.col_offset)] = (
                    arg.end_col_offset - arg.col_offset, new)
    return out


def _apply_rewrites(lines: list[str], rewrites: dict) -> list[str]:
    """줄 안의 리터럴만 바꾼다. 나머지 글자는 건드리지 않는다 — 주석과
    서식이 사라지면 병합 파일을 사람이 이어서 고칠 수 없다."""
    if not rewrites:
        return lines
    out = list(lines)
    # 한 줄에 여러 개면 뒤에서부터 — 앞을 먼저 바꾸면 뒤의 열 번호가 밀린다
    for (ln, col), (width, new) in sorted(rewrites.items(), reverse=True):
        if not 1 <= ln <= len(out):
            continue
        text = out[ln - 1]
        out[ln - 1] = text[:col] + repr(new) + text[col + width:]
    return out


def inline_panel(source: str, func: str, name: str, label: str = "",
                 arg: str = "ax", from_dir=None, to_dir=None) -> str:
    """패널 소스를 `def {name}(ax):` 블록 하나로 만든다.

    func는 ax를 받는 함수 이름(보통 plot)이다. 감싼 함수의 마지막 줄에서
    그것을 호출하므로, 호출부는 {name}(ax) 하나만 알면 된다.

    arg는 받는 이름이다. 축을 여러 개 쓰는 패널에는 목록을 건네므로 axs가
    된다 — 이름이 곧 하나인지 여럿인지를 말한다.

    from_dir/to_dir을 주면 데이터 경로를 병합 파일에서 보이는 상대 경로로
    고쳐 옮긴다. 원본 파일은 건드리지 않는다 — 고쳐지는 것은 여기서 만드는
    사본뿐이다.
    """
    where = label or _t("패널")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise InlineError(_t("{where}를 해석하지 못했습니다: {err}",
                             where=where, err=exc)) from exc

    if not _defines(tree, func):
        raise InlineError(_t(
            "{where}에 ax를 받는 {func}() 함수가 없습니다.",
            where=where, func=func))

    if _uses_file(tree):
        raise InlineError(_t(
            "{where}가 __file__을 씁니다. 병합 파일 안으로 옮기면 그 값이 "
            "병합 파일의 경로가 되어 다른 파일을 읽게 됩니다. 경로를 "
            "인자나 상수로 바꾼 뒤 다시 시도하세요.", where=where))

    # 버릴 줄 범위를 모은다. 원문을 그대로 옮기려면 재조립이 아니라 줄
    # 단위로 덜어내야 주석과 서식이 남는다.
    drop: set[int] = set()
    for node in tree.body:
        if _main_guard(node) or _future_import(node):
            drop.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))

    lines = source.splitlines()
    if from_dir is not None and to_dir is not None:
        lines = _apply_rewrites(
            lines, _rewrites(tree, Path(from_dir), Path(to_dir)))
    kept = [ln for i, ln in enumerate(lines, start=1) if i not in drop]
    # 앞뒤 빈 줄은 감싼 함수 안에서 뜻이 없다
    while kept and not kept[0].strip():
        kept.pop(0)
    while kept and not kept[-1].strip():
        kept.pop()

    body = "\n".join(("    " + ln) if ln.strip() else "" for ln in kept)
    # 마지막 호출을 원문과 한 줄 떼어 놓는다. 붙어 있으면 옮겨 온 코드의
    # 일부인지 우리가 붙인 것인지 구별되지 않는다.
    return f"def {name}({arg}):\n{body}\n\n    {func}({arg})\n"
