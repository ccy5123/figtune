"""matplotlib이 이름을 가진 색들.

세 묶음이다 — 기본 8색(b/g/r/…), Tableau 10색(기본 색 순환), CSS 148색.
색 선택을 운영체제 색상환에만 맡기면 그림 안의 다른 선과 같은 색을 다시
고를 방법이 없다. matplotlib이 이미 아는 이름을 그대로 내주면, 코드에 적힌
'tab:blue'와 화면에서 고른 색이 같은 것이 된다.

값은 hex로 낸다. spec은 색을 hex 정규형으로 접으므로(props.normalize),
이름을 그대로 흘려보내면 저장 직후 이름이 hex로 바뀌어 화면과 어긋난다.
이름은 표시와 검색에만 쓴다.

CSS는 이름 순이 아니라 색상환 순으로 낸다. 148개를 알파벳순으로 늘어놓으면
비슷한 색이 목록 곳곳에 흩어져, 원하는 색을 찾으려면 전부 읽어야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import matplotlib.colors as mcolors

from ..i18n import t as _t


@dataclass(frozen=True)
class Swatch:
    name: str
    hex: str


@dataclass(frozen=True)
class Group:
    key: str
    label: str          # 사용자에게 보일 이름
    swatches: list[Swatch]
    collapsed: bool     # 접어 두고 +로 펼칠 묶음인가


def _hex(value) -> str:
    return mcolors.to_hex(value, keep_alpha=False)


def _by_hue(colors: dict[str, str]) -> list[Swatch]:
    """색상환 순. 같은 색상 안에서는 채도·명도, 마지막으로 이름 순.

    이름을 마지막 열쇠로 두어야 회색 계열(색상·채도가 모두 0)에서도 순서가
    한 가지로 정해진다. 그렇지 않으면 실행할 때마다 목록이 뒤바뀐다.
    """
    def key(item):
        name, value = item
        h, s, v = mcolors.rgb_to_hsv(mcolors.to_rgb(value))
        return (h, s, v, name)

    return [Swatch(name, _hex(value))
            for name, value in sorted(colors.items(), key=key)]


BASE = [Swatch(n, _hex(v)) for n, v in mcolors.BASE_COLORS.items()]
TABLEAU = [Swatch(n, _hex(v)) for n, v in mcolors.TABLEAU_COLORS.items()]
CSS = _by_hue(mcolors.CSS4_COLORS)


def groups() -> list[Group]:
    """팔레트에 보일 묶음. 순서대로 위에서 아래로.

    CSS만 접어 둔다. 148개를 처음부터 펼치면 자주 쓰는 앞의 18개가 화면
    밖으로 밀려나, 흔한 선택이 가장 먼 선택이 된다.
    """
    return [
        Group("base", _t("기본 색"), BASE, collapsed=False),
        Group("tableau", "Tableau", TABLEAU, collapsed=False),
        Group("css", _t("CSS 색"), CSS, collapsed=True),
    ]


def name_of(value: str) -> str | None:
    """이 색의 이름. 없으면 None.

    같은 색에 이름이 여럿이면(gray/grey) 먼저 나온 묶음의 것을 쓴다 —
    기본 색, Tableau, CSS 순. 짧고 익숙한 쪽이 앞에 온다.
    """
    try:
        want = _hex(value)
    except (ValueError, TypeError):
        return None
    for group in groups():
        for sw in group.swatches:
            if sw.hex == want:
                return sw.name
    return None
