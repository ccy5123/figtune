"""축 상자가 figure 밖으로 나가면 figure를 키운다.

축을 끌어 넓히다 보면 흰 종이(figure) 밖으로 나가고, 나간 만큼은 잘려서
보이지 않는다. 사용자가 원한 것은 '자르기'가 아니라 '종이를 키우기'다.

계산은 인치로 한다. figure 좌표(0~1)로 하면 종이가 커지는 순간 같은 0.5가
다른 물리 위치를 뜻하게 되어, 건드리지 않은 패널까지 따라 움직인다. 인치로
잡아 두고 마지막에 새 크기로 나누면 나머지 패널은 제자리에 남는다.

Qt를 import하지 않는다 — Figure 기하일 뿐이고, GUI 없이 테스트된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import selector as sel

# 이보다 작은 차이는 무시한다. 부동소수점 오차로 종이가 계속 자라면
# 끌 때마다 캔버스가 미세하게 떨린다.
EPS = 1e-4

# 내용과 종이 가장자리 사이에 남길 여백(인치). matplotlib의
# savefig(bbox_inches="tight") 기본값과 같은 값이라 눈에 익다.
MARGIN = 0.1


@dataclass(frozen=True)
class Growth:
    """종이를 키운 결과. 그대로 set_prop에 넣으면 된다."""

    size_inches: list                       # 새 figure 크기
    positions: dict = field(default_factory=dict)   # selector -> 새 축 상자

    def changes(self) -> list[tuple[str, str, list]]:
        out = [("fig", "size_inches", self.size_inches)]
        out += [(path, "position", box)
                for path, box in sorted(self.positions.items())]
        return out


def _boxes_in_inches(fig):
    """인치 단위 축 상자들. numpy 스칼라는 여기서 걷어낸다.

    matplotlib이 돌려주는 값은 np.float64라, 그대로 두면 spec 직전까지
    딸려 다니다가 상태줄이나 로그에 np.float64(...)로 새어 나온다.
    """
    w_in, h_in = (float(v) for v in fig.get_size_inches())
    out = []
    for ax in fig.axes:
        x0, y0, w, h = (float(v) for v in ax.get_position().bounds)
        out.append([x0 * w_in, y0 * h_in, w * w_in, h * h_in])
    return out, w_in, h_in


def _tight_extent(fig, renderer=None):
    """제목·축라벨·눈금·범례까지 포함해 실제로 차지하는 범위(인치).

    축 상자만 보면 안 된다. 제목과 축 라벨은 상자 **밖**에 그려지므로,
    상자가 [0,1] 안에 있어도 글자는 종이 밖으로 나가 잘린다. 세로로 길게
    늘렸을 때 제목이 사라지는 것이 그 증상이다.
    """
    try:
        r = renderer if renderer is not None else fig.canvas.get_renderer()
        bb = fig.get_tightbbox(r)
    except Exception:                    # pragma: no cover - 백엔드 차이
        return None
    if bb is None:
        return None
    return float(bb.x0), float(bb.y0), float(bb.x1), float(bb.y1)


def fit_to_content(fig, renderer=None, margin: float = MARGIN) -> Growth | None:
    """종이를 내용에 맞춘다. 이미 맞으면 None.

    규칙은 하나다 — **종이 = 모든 구성요소의 경계 + 여백.** 네 방향이 같게
    동작하고, 늘기도 줄기도 한다. 제목을 올리면 위가 늘고, 처음보다 내리면
    처음보다 줄어든다.

    경계는 제목·축라벨·눈금·범례까지 포함한 tight bbox다. 축 상자만 보면
    상자가 [0,1] 안이어도 글자는 밖으로 나가 잘린다.

    글자는 포인트 단위라 종이 크기가 바뀌어도 인치 크기가 그대로다. 그래서
    축 상자를 같은 만큼 밀고 새 크기로 나누면 제목·라벨이 함께 따라온다.
    """
    if not fig.axes:
        return None

    boxes, w_in, h_in = _boxes_in_inches(fig)
    tight = _tight_extent(fig, renderer)
    if tight is None:
        # 렌더러가 없으면 상자만으로 판단한다. 글자 넘침은 못 잡지만
        # 아무것도 안 하는 것보다는 낫다.
        tight = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                 max(b[0] + b[2] for b in boxes),
                 max(b[1] + b[3] for b in boxes))

    new_w = (tight[2] - tight[0]) + 2 * margin
    new_h = (tight[3] - tight[1]) + 2 * margin
    dx, dy = margin - tight[0], margin - tight[1]

    if abs(new_w - w_in) < EPS and abs(new_h - h_in) < EPS \
            and abs(dx) < EPS and abs(dy) < EPS:
        return None

    positions = {}
    for i, (x0, y0, w, h) in enumerate(boxes):
        positions[sel.axes(i)] = [round((x0 + dx) / new_w, 6),
                                  round((y0 + dy) / new_h, 6),
                                  round(w / new_w, 6),
                                  round(h / new_h, 6)]
    return Growth(size_inches=[round(new_w, 4), round(new_h, 4)],
                  positions=positions)
