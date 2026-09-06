"""여러 figure를 하나로 합친다 (montage).

── 왜 axes를 옮기지 않는가 ──────────────────────────────────────────
matplotlib은 figure 사이의 axes 이동을 지원하지 않는다. `ax.figure = other`
로 대입하든 `ax.set_figure(other)`를 쓰든, transform 체인이 낡은 채 남아
눈금이 뭉개지고 내용이 잘린다. 실측으로 확인했다.

그래서 합성은 **SVG 레벨**에서 한다. 각 패널을 따로 렌더한 뒤 벡터 상태로
배치한다. 텍스트는 텍스트로, 선은 선으로 남는다. 부수 효과로 각 패널은
자기 스크립트/spec으로 독립 편집이 가능한 상태를 유지한다 — figtune의
전제("원본 코드를 구조적으로 건드리지 않는다")가 깨지지 않는다.
─────────────────────────────────────────────────────────────────────

── axes 정렬 ────────────────────────────────────────────────────────
단순 타일링은 논문 그림으로 쓸 수 없다. y축 라벨 길이가 다르면 패널마다
그림틀(plot box) 위치가 어긋나기 때문이다. 그래서 이미지 경계가 아니라
**axes 상자**를 기준으로 맞춘다. 각 패널의 axes 위치는 알 수 있으므로
(ax.get_position() × figure 크기) 열마다 왼쪽 모서리를, 행마다 아래
모서리를 정렬하고, axes 폭/높이가 같아지도록 배율을 준다.
─────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from ..i18n import t as _t

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

_LEN_RE = re.compile(r"^([0-9.]+)\s*(pt|px|in|mm|cm)?$")
_UNIT_PT = {"pt": 1.0, "px": 0.75, "in": 72.0, "mm": 72 / 25.4, "cm": 72 / 2.54}


def _to_pt(value: str) -> float:
    m = _LEN_RE.match((value or "").strip())
    if not m:
        return 0.0
    return float(m.group(1)) * _UNIT_PT.get(m.group(2) or "px", 0.75)


@dataclass
class Panel:
    """합성에 들어갈 패널 하나."""
    svg: str                       # 렌더된 SVG 소스
    axes_box: tuple                # (l, b, w, h) — figure 좌표 fraction
    fig_size: tuple                # (width_in, height_in)
    label: str = ""                # (a), (b) …

    @property
    def size_pt(self) -> tuple:
        return (self.fig_size[0] * 72.0, self.fig_size[1] * 72.0)

    def axes_rect_pt(self) -> tuple:
        """SVG 좌표계(원점 좌상단) 기준 axes 상자."""
        w_pt, h_pt = self.size_pt
        l, b, w, h = self.axes_box
        return (l * w_pt, (1.0 - b - h) * h_pt, w * w_pt, h * h_pt)


def panel_from_figure(fig, svg_source: str, axes_index: int = 0,
                      label: str = "") -> Panel:
    """살아있는 Figure에서 정렬에 필요한 기하 정보를 뽑는다."""
    ax = fig.axes[axes_index]
    pos = ax.get_position()
    return Panel(svg=svg_source, axes_box=(pos.x0, pos.y0, pos.width, pos.height),
                 fig_size=tuple(fig.get_size_inches()), label=label)


# --- id 격리 ---------------------------------------------------------------

_ID_ATTR = re.compile(r'\bid="([^"]+)"')


def namespace_ids(svg: str, prefix: str) -> str:
    """SVG 안의 모든 id와 그 참조에 접두사를 붙인다.

    matplotlib SVG 하나에 id가 수십 개, 참조가 수십 개 들어 있다. 격리하지
    않고 합치면 뒤 패널의 글리프가 앞 패널 것으로 바뀌는 식으로 조용히
    망가진다.
    """
    ids = set(_ID_ATTR.findall(svg))
    if not ids:
        return svg
    # 긴 id부터 치환해야 짧은 id가 부분 문자열로 잘못 걸리지 않는다
    for old in sorted(ids, key=len, reverse=True):
        new = f"{prefix}{old}"
        svg = svg.replace(f'id="{old}"', f'id="{new}"')
        svg = svg.replace(f'href="#{old}"', f'href="#{new}"')
        svg = svg.replace(f"url(#{old})", f"url(#{new})")
    return svg


def _inner(svg: str) -> tuple[str, float, float]:
    """루트 <svg>의 내용과 크기(pt)를 돌려준다."""
    root = ET.fromstring(svg)
    w = _to_pt(root.get("width", ""))
    h = _to_pt(root.get("height", ""))
    if not w or not h:
        vb = (root.get("viewBox") or "").split()
        if len(vb) == 4:
            w, h = float(vb[2]), float(vb[3])
    body = "".join(ET.tostring(child, encoding="unicode") for child in root)
    return body, w, h


# --- 합성 -----------------------------------------------------------------

@dataclass
class MontageResult:
    svg: str
    size_pt: tuple
    placements: list = field(default_factory=list)   # 패널별 axes 상자(합성 좌표)


def fit_axes_size(fig, target_w_in: float, target_h_in: float,
                  axes_index: int = 0) -> None:
    """axes 상자가 정확히 target 크기가 되도록 figure를 다시 잡는다.

    이미지를 배율로 줄여 맞추면 두 가지 중 하나를 잃는다. 균일 배율은
    종횡비가 다른 패널의 가로세로를 동시에 맞출 수 없고, 비균일 배율은
    글씨와 마커를 찌그러뜨린다. 논문 그림에서 둘 다 받아들일 수 없다.

    그래서 배율 대신 **figure를 다시 잡는다.** 축 라벨·눈금이 차지하는
    여백은 인치 단위로 그대로 두고, 그림틀만 목표 크기로 만든 뒤 다시
    렌더하면 배율 1로 정확히 일치한다.
    """
    ax = fig.axes[axes_index]
    W, H = fig.get_size_inches()
    pos = ax.get_position()

    pad_l, pad_r = pos.x0 * W, (1.0 - pos.x0 - pos.width) * W
    pad_b, pad_t = pos.y0 * H, (1.0 - pos.y0 - pos.height) * H

    new_W = target_w_in + pad_l + pad_r
    new_H = target_h_in + pad_b + pad_t
    if new_W <= 0 or new_H <= 0:
        raise ValueError(_t("여백이 목표 크기보다 큽니다. target을 키우세요."))

    fig.set_size_inches(new_W, new_H)
    ax.set_position([pad_l / new_W, pad_b / new_H,
                     target_w_in / new_W, target_h_in / new_H])


def axes_size_inches(fig, axes_index: int = 0) -> tuple:
    W, H = fig.get_size_inches()
    pos = fig.axes[axes_index].get_position()
    return (pos.width * W, pos.height * H)


def compose(panels: list[Panel], rows: int, cols: int,
            align: str = "axes", gap_pt: float = 14.0, margin_pt: float = 4.0,
            label_offset_pt: tuple = (2.0, 10.0),
            label_style: str = "font-family:sans-serif;font-size:11px;"
                               "font-weight:bold") -> MontageResult:
    """패널들을 rows×cols 격자로 합친다.

    align="axes"  — axes 상자를 기준으로 정렬 (논문용 기본값)
    align="bbox"  — 이미지 경계 기준 단순 타일링
    """
    if len(panels) > rows * cols:
        raise ValueError(_t("패널 {n}개는 {rows}×{cols} 격자에 넘칩니다.",
                            n=len(panels), rows=rows, cols=cols))

    prepared = []
    for i, p in enumerate(panels):
        body, w, h = _inner(namespace_ids(p.svg, f"p{i}_"))
        prepared.append((p, body, w, h))

    if align == "axes":
        # 모든 패널의 axes 크기를 가장 작은 것에 맞춘다 (확대는 하지 않는다)
        target_w = min(p.axes_rect_pt()[2] for p, _, _, _ in prepared)
        target_h = min(p.axes_rect_pt()[3] for p, _, _, _ in prepared)
        scales = []
        for p, _, _, _ in prepared:
            _, _, aw, ah = p.axes_rect_pt()
            scales.append(min(target_w / aw, target_h / ah))
    else:
        scales = [1.0] * len(prepared)

    # 각 패널의 axes 왼쪽/위 여백과 오른쪽/아래 여백 (배율 적용 후)
    metrics = []
    for (p, _, w, h), s in zip(prepared, scales):
        ax_l, ax_t, ax_w, ax_h = [v * s for v in p.axes_rect_pt()]
        metrics.append({"pad_l": ax_l, "pad_t": ax_t,
                        "pad_r": w * s - ax_l - ax_w,
                        "pad_b": h * s - ax_t - ax_h,
                        "ax_w": ax_w, "ax_h": ax_h, "w": w * s, "h": h * s})

    # 열마다 왼쪽 여백의 최댓값을 쓰면 axes 왼쪽 모서리가 일직선이 된다
    col_pad_l = [max((metrics[r * cols + c]["pad_l"]
                      for r in range(rows) if r * cols + c < len(metrics)),
                     default=0.0) for c in range(cols)]
    col_ax_w = [max((metrics[r * cols + c]["ax_w"]
                     for r in range(rows) if r * cols + c < len(metrics)),
                    default=0.0) for c in range(cols)]
    col_pad_r = [max((metrics[r * cols + c]["pad_r"]
                      for r in range(rows) if r * cols + c < len(metrics)),
                     default=0.0) for c in range(cols)]
    row_pad_t = [max((metrics[r * cols + c]["pad_t"]
                      for c in range(cols) if r * cols + c < len(metrics)),
                     default=0.0) for r in range(rows)]
    row_ax_h = [max((metrics[r * cols + c]["ax_h"]
                     for c in range(cols) if r * cols + c < len(metrics)),
                    default=0.0) for r in range(rows)]
    row_pad_b = [max((metrics[r * cols + c]["pad_b"]
                      for c in range(cols) if r * cols + c < len(metrics)),
                     default=0.0) for r in range(rows)]

    col_x, x = [], 0.0
    for c in range(cols):
        col_x.append(x)
        x += col_pad_l[c] + col_ax_w[c] + col_pad_r[c] + (gap_pt if c < cols - 1 else 0)
    total_w = x

    row_y, y = [], 0.0
    for r in range(rows):
        row_y.append(y)
        y += row_pad_t[r] + row_ax_h[r] + row_pad_b[r] + (gap_pt if r < rows - 1 else 0)
    total_h = y

    # 라벨은 axes 위쪽에 그려진다. 제목이 없는 패널은 위 여백이 거의 없어
    # 라벨이 음수 좌표로 나가 잘린다. 필요한 만큼 위 여백을 더 확보한다.
    label_h = _label_height(label_style)
    need_top = 0.0
    for i, (p, _, _, _) in enumerate(prepared):
        if not p.label:
            continue
        r, c = divmod(i, cols)
        ly = row_y[r] + row_pad_t[r] - label_offset_pt[1]
        need_top = max(need_top, label_h - ly)

    # 경계에 딱 붙은 텍스트는 렌더러가 깎아낸다. 사방에 여백을 둔다.
    off_x = margin_pt
    off_y = margin_pt + max(0.0, need_top)
    total_w += 2 * margin_pt
    total_h += off_y + margin_pt

    parts, placements = [], []
    for i, ((p, body, w, h), s, m) in enumerate(zip(prepared, scales, metrics)):
        r, c = divmod(i, cols)
        # axes 왼쪽/위 모서리가 격자 기준선에 오도록 패널 전체를 민다
        tx = off_x + col_x[c] + col_pad_l[c] - m["pad_l"]
        ty = off_y + row_y[r] + row_pad_t[r] - m["pad_t"]
        parts.append(
            f'<g transform="translate({tx:.3f},{ty:.3f}) scale({s:.6f})">'
            f"{body}</g>")
        ax_x = off_x + col_x[c] + col_pad_l[c]
        ax_y = off_y + row_y[r] + row_pad_t[r]
        placements.append({"index": i, "row": r, "col": c,
                           "axes_x": round(ax_x, 3), "axes_y": round(ax_y, 3),
                           "axes_w": round(m["ax_w"], 3),
                           "axes_h": round(m["ax_h"], 3),
                           "scale": round(s, 6)})
        if p.label:
            lx = ax_x + label_offset_pt[0]
            ly = ax_y - label_offset_pt[1]
            parts.append(
                f'<text x="{lx:.2f}" y="{ly:.2f}" style="{label_style}">'
                f"{_escape(p.label)}</text>")

    svg = (f'<svg xmlns="{SVG_NS}" xmlns:xlink="{XLINK_NS}" version="1.1" '
           f'width="{total_w:.3f}pt" height="{total_h:.3f}pt" '
           f'viewBox="0 0 {total_w:.3f} {total_h:.3f}">'
           f'<rect width="{total_w:.3f}" height="{total_h:.3f}" fill="white"/>'
           + "".join(parts) + "</svg>")
    return MontageResult(svg=svg, size_pt=(total_w, total_h),
                         placements=placements)


def _label_height(style: str) -> float:
    m = re.search(r"font-size:\s*([0-9.]+)", style or "")
    return float(m.group(1)) if m else 11.0


def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def default_labels(n: int, template: str = "({a})") -> list[str]:
    return [template.format(a=chr(ord("a") + i), A=chr(ord("A") + i), n=i + 1)
            for i in range(n)]


def write(result: MontageResult, svg_path: Path | str) -> Path:
    p = Path(svg_path)
    p.write_text(result.svg, encoding="utf-8")
    return p


def to_png(svg_path: Path | str, png_path: Path | str, dpi: int = 300) -> Path:
    """PNG 대체본을 만든다. 공유 안전성을 위해 항상 함께 둔다.

    cairosvg가 있으면 그것을, 없으면 matplotlib이 이미 만든 PNG 경로를
    쓰도록 호출자가 처리해야 한다.
    """
    try:
        import cairosvg
    except ImportError as exc:                       # pragma: no cover
        raise RuntimeError(_t(
            "SVG→PNG 변환에는 cairosvg가 필요합니다 (pip install cairosvg). "
            "설치가 어려우면 벡터 없이 패널을 PNG로 합성하세요.")) from exc
    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), dpi=dpi)
    return Path(png_path)
