"""Artist 주소 지정.

selector는 사람이 읽을 수 있는 경로 문자열이다. 예:

    fig                     Figure 자체
    ax0                     fig.axes[0]
    ax0.line1               fig.axes[0].lines[1]
    ax0.coll0               fig.axes[0].collections[0]
    ax0.patch2              fig.axes[0].patches[2]
    ax0.title               fig.axes[0].title      (Text)
    ax0.xlabel              fig.axes[0].xaxis.label
    ax0.spine:top           fig.axes[0].spines['top']
    ax0.xtick.major         x축 major tick 그룹
    ax0.grid.y              y축 grid
    ax0.legend              범례
    ax0.text:t001           figtune이 추가한 텍스트

설계 결정: 설계문 3절의 중첩 스키마 대신 평탄한 selector→props 매핑을 쓴다.
표현력은 같고 YAML이 훨씬 읽기 쉬우며 undo 스택 구현이 단순해진다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 컨테이너 종류 → Axes 속성 이름
_SEQ = {"line": "lines", "coll": "collections", "patch": "patches",
        # 사용자 스크립트가 ax.text()/annotate()로 만든 텍스트.
        # figtune이 추가한 것(text:tNNN)과 구분해야 한다 — 전자는 원본 코드
        # 소유라 override만 걸고, 후자는 figtune 소유라 지울 수도 있다.
        "txt": "texts"}
_SEQ_PREFIX = {v: k for k, v in _SEQ.items()}

_AX_RE = re.compile(r"^ax(\d+)$")
_SEQ_RE = re.compile(r"^(line|coll|patch|txt)(\d+)$")


class SelectorError(ValueError):
    pass


@dataclass(frozen=True)
class Selector:
    """selector 경로의 파싱된 형태."""

    path: str
    kind: str           # figure|axes|line|coll|patch|text|spine|tick|grid|legend|usertext
    axes: int | None = None
    index: int | None = None
    name: str | None = None      # spine 이름, tick 축, user text id
    which: str | None = None     # tick의 major/minor

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.path


def parse(path: str) -> Selector:
    """selector 문자열을 Selector로 파싱한다."""
    if path == "fig":
        return Selector(path, "figure")

    # figure 수준 텍스트 (suptitle, fig.text(...))
    if path == "fig.suptitle":
        return Selector(path, "figtext", name="suptitle")
    m = re.match(r"^fig\.txt(\d+)$", path)
    if m:
        return Selector(path, "figtext", index=int(m.group(1)))

    # figure 수준 범례. seaborn FacetGrid는 범례를 여기에 단다.
    if path == "fig.legend":
        return Selector(path, "figlegend", index=0)

    head, _, rest = path.partition(".")
    m = _AX_RE.match(head)
    if not m:
        raise SelectorError(f"알 수 없는 selector: {path!r}")
    ax = int(m.group(1))

    if not rest:
        return Selector(path, "axes", axes=ax)

    if rest in ("title", "xlabel", "ylabel"):
        return Selector(path, "text", axes=ax, name=rest)

    if rest == "legend":
        return Selector(path, "legend", axes=ax)

    m = _SEQ_RE.match(rest)
    if m:
        return Selector(path, m.group(1), axes=ax, index=int(m.group(2)))

    if rest.startswith("spine:"):
        return Selector(path, "spine", axes=ax, name=rest.split(":", 1)[1])

    if rest.startswith("text:"):
        return Selector(path, "usertext", axes=ax, name=rest.split(":", 1)[1])

    m = re.match(r"^([xy])tick\.(major|minor)$", rest)
    if m:
        return Selector(path, "tick", axes=ax, name=m.group(1), which=m.group(2))

    m = re.match(r"^grid\.([xy])$", rest)
    if m:
        return Selector(path, "grid", axes=ax, name=m.group(1))

    raise SelectorError(f"알 수 없는 selector: {path!r}")


# --- 생성 헬퍼 -------------------------------------------------------------

def axes(i: int) -> str:
    return f"ax{i}"


def seq(ax_i: int, container: str, j: int) -> str:
    """container는 'lines' | 'collections' | 'patches'."""
    return f"ax{ax_i}.{_SEQ_PREFIX[container]}{j}"


def text(ax_i: int, which: str) -> str:
    return f"ax{ax_i}.{which}"


def spine(ax_i: int, name: str) -> str:
    return f"ax{ax_i}.spine:{name}"


def tick(ax_i: int, axis: str, which: str = "major") -> str:
    return f"ax{ax_i}.{axis}tick.{which}"


def grid(ax_i: int, axis: str) -> str:
    return f"ax{ax_i}.grid.{axis}"


def legend(ax_i: int) -> str:
    return f"ax{ax_i}.legend"


def usertext(ax_i: int, tid: str) -> str:
    return f"ax{ax_i}.text:{tid}"


# --- 해석 -----------------------------------------------------------------

def figtext(index=None, sup=False) -> str:
    return "fig.suptitle" if sup else f"fig.txt{index}"


def resolve(fig, path: str):
    """살아있는 Figure에서 selector가 가리키는 객체를 반환한다.

    tick/grid/legend처럼 단일 artist가 아닌 대상은 (fig, ax) 문맥이 필요하므로
    apply 단계에서 별도 처리한다. 여기서는 Axes를 반환한다.
    """
    s = parse(path)
    if s.kind == "figure":
        return fig
    if s.kind == "figtext":
        if s.name == "suptitle":
            t = getattr(fig, "_suptitle", None)
            if t is None:
                raise SelectorError("suptitle 없음")
            return t
        try:
            return fig.texts[s.index]
        except IndexError as exc:
            raise SelectorError(f"{path} 없음") from exc
    if s.kind == "figlegend":
        if not getattr(fig, "legends", None):
            raise SelectorError("figure 범례 없음")
        return fig.legends[0]

    try:
        ax = fig.axes[s.axes]
    except IndexError as exc:
        raise SelectorError(f"axes[{s.axes}] 없음 ({path})") from exc

    if s.kind in ("axes", "tick", "grid", "legend"):
        return ax

    if s.kind in _SEQ:
        container = getattr(ax, _SEQ[s.kind])
        try:
            return container[s.index]
        except IndexError as exc:
            raise SelectorError(f"{path} 없음 (개수 {len(container)})") from exc

    if s.kind == "text":
        return {"title": ax.title,
                "xlabel": ax.xaxis.label,
                "ylabel": ax.yaxis.label}[s.name]

    if s.kind == "spine":
        try:
            return ax.spines[s.name]
        except KeyError as exc:
            raise SelectorError(f"spine {s.name!r} 없음") from exc

    if s.kind == "usertext":
        for t in ax.texts:
            if getattr(t, "_figtune_id", None) == s.name:
                return t
        raise SelectorError(f"user text {s.name!r} 없음")

    raise SelectorError(f"해석 불가: {path!r}")


def code_expr(path: str) -> str:
    """codegen이 쓸 Python 표현식. 변수 axN은 미리 선언되어 있다고 가정."""
    s = parse(path)
    if s.kind == "figure":
        return "fig"
    if s.kind == "figtext":
        return ("fig._suptitle" if s.name == "suptitle"
                else f"fig.texts[{s.index}]")
    if s.kind == "figlegend":
        return "fig"
    var = f"ax{s.axes}"
    if s.kind in ("axes", "tick", "grid", "legend"):
        return var
    if s.kind in _SEQ:
        return f"{var}.{_SEQ[s.kind]}[{s.index}]"
    if s.kind == "text":
        return {"title": f"{var}.title",
                "xlabel": f"{var}.xaxis.label",
                "ylabel": f"{var}.yaxis.label"}[s.name]
    if s.kind == "spine":
        return f"{var}.spines[{s.name!r}]"
    raise SelectorError(f"코드 표현식 불가: {path!r}")
