"""Figure → 편집 가능한 노드 트리.

GUI 트리뷰와 인스펙터가 이 결과를 소비한다. spec은 여기서 만들지 않는다
(원칙 1: 명시된 키만 override가 된다. 초기 추출은 '현재값 표시'용일 뿐이다).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..i18n import t as _t
from . import fingerprint as fp
from . import props as P
from . import selector as sel


@dataclass
class Node:
    path: str
    kind: str
    label: str
    children: list["Node"] = field(default_factory=list)
    fingerprint: dict | None = None
    pickable: bool = False       # 캔버스에서 직접 클릭 가능한가

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


def _label_of(artist, fallback: str) -> str:
    try:
        lb = artist.get_label()
    except Exception:
        return fallback
    lb = str(lb)
    if not lb or lb.startswith("_"):
        return fallback
    return lb


def _marked(label: str, empty: bool) -> str:
    """그릴 것이 없는 artist임을 라벨이 스스로 밝히게 한다.

    seaborn은 hue 범례를 만들려고 데이터 점이 0개인 Line2D를 축에 남긴다.
    이름은 실제 계열('high')과 구별되지 않으므로, 표시하지 않으면 색을
    바꿔도 화면에 아무 일이 없는 이유를 사용자가 알 방법이 없다. 편집을
    막지는 않는다 — 값은 spec에 남고, 범례를 다시 그리면 반영된다.
    """
    return f"{label} {_t('(범례 전용)')}" if empty else label


def build(fig) -> Node:
    """살아있는 Figure를 노드 트리로 변환한다."""
    root = Node("fig", "figure", "Figure", fingerprint=fp.of_figure(fig))

    # figure 수준 텍스트. suptitle이나 fig.text()로 넣은 주석이 여기 산다.
    # 축에 붙어 있지 않아 지금까지 편집 대상에서 통째로 빠져 있었다.
    sup = getattr(fig, "_suptitle", None)
    if sup is not None and sup.get_text():
        root.children.append(Node("fig.suptitle", "figtext",
                                  f"suptitle: {sup.get_text()[:28]}",
                                  pickable=True))
    for j, t in enumerate(fig.texts):
        if t is sup:
            continue
        root.children.append(Node(f"fig.txt{j}", "figtext",
                                  f"fig.txt{j} — {t.get_text()[:24]}",
                                  pickable=True))

    if getattr(fig, "legends", None):
        root.children.append(Node("fig.legend", "figlegend",
                                  "figure legend", pickable=False))

    for i, ax in enumerate(fig.axes):
        axn = Node(sel.axes(i), "axes", f"Axes {i}", fingerprint=fp.of_axes(ax))
        root.children.append(axn)

        # 텍스트 요소
        for which, art in (("title", ax.title),
                           ("xlabel", ax.xaxis.label),
                           ("ylabel", ax.yaxis.label)):
            txt = art.get_text()
            shown = txt if txt else _t("(비어 있음)")
            axn.children.append(
                Node(sel.text(i, which), "text", f"{which}: {shown}", pickable=True))

        # 데이터 artist
        for j, ln in enumerate(ax.lines):
            f = fp.of_line(ln)
            axn.children.append(Node(
                sel.seq(i, "lines", j), "line",
                _marked(f"line{j} — {_label_of(ln, _t('(라벨 없음)'))}",
                        f["n"] == 0),
                fingerprint=f, pickable=True))

        for j, cl in enumerate(ax.collections):
            f = fp.of_collection(cl)
            axn.children.append(Node(
                sel.seq(i, "collections", j), "coll",
                _marked(f"coll{j} — {_label_of(cl, _t('(라벨 없음)'))}",
                        f["n"] == 0),
                fingerprint=f, pickable=True))

        if ax.patches:
            grp = Node(f"{sel.axes(i)}.patches", "group",
                       f"patches ({len(ax.patches)})",
                       fingerprint=fp.of_patch_group(ax.patches))
            for j in range(len(ax.patches)):
                grp.children.append(
                    Node(sel.seq(i, "patches", j), "patch", f"patch{j}", pickable=True))
            axn.children.append(grp)

        # spine
        spg = Node(f"{sel.axes(i)}.spines", "group", "spines")
        for name in ("left", "right", "top", "bottom"):
            if name in ax.spines:
                spg.children.append(
                    Node(sel.spine(i, name), "spine", name, pickable=True))
        axn.children.append(spg)

        # tick / grid
        tg = Node(f"{sel.axes(i)}.ticks", "group", "ticks")
        for axis in ("x", "y"):
            for which in ("major", "minor"):
                tg.children.append(
                    Node(sel.tick(i, axis, which), "tick", f"{axis} {which}"))
        axn.children.append(tg)

        gg = Node(f"{sel.axes(i)}.grids", "group", "grid")
        for axis in ("x", "y"):
            gg.children.append(Node(sel.grid(i, axis), "grid", f"{axis} grid"))
        axn.children.append(gg)

        axn.children.append(Node(sel.legend(i), "legend", "legend"))

        # 텍스트 두 종류를 모두 보여준다.
        #   원본 스크립트가 만든 것 → override만 (지우지 않는다)
        #   figtune이 추가한 것     → 이동·삭제까지
        for j, t in enumerate(ax.texts):
            tid = getattr(t, "_figtune_id", None)
            if tid:
                axn.children.append(Node(
                    sel.usertext(i, tid), "usertext",
                    f"text:{tid} — {t.get_text()[:24]}", pickable=True))
            else:
                axn.children.append(Node(
                    sel.seq(i, "texts", j), "txt",
                    f"txt{j} — {t.get_text()[:24] or _t('(비어 있음)')}",
                    fingerprint=fp.of_text(t), pickable=True))

    return root


def fingerprints(fig) -> dict[str, dict]:
    """저장용 지문 맵."""
    out: dict[str, dict] = {}
    for n in build(fig).walk():
        if n.fingerprint is not None:
            out[n.path] = n.fingerprint
    return out


def current_values(fig, path: str) -> dict:
    """인스펙터가 표시할 현재 실제 값들 (spec override 아님)."""
    kind = sel.parse(path).kind
    return {p.name: P.get(fig, path, p.name) for p in P.props_for(kind)}


def check_stale(fig, stored: dict[str, dict]) -> dict[str, dict]:
    """저장된 지문과 현재 figure를 대조한다.

    반환: {selector: {"stored":…, "current":…, "suggest": path|None}}
    """
    now = fingerprints(fig)
    bad: dict[str, dict] = {}
    for path, old in stored.items():
        cur = now.get(path)
        if cur is None or not fp.matches(old, cur):
            bad[path] = {"stored": old, "current": cur,
                         "suggest": fp.relabel_candidate(old, now)}
    return bad
