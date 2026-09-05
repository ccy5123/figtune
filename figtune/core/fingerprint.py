"""Fingerprint.

인덱스 기반 주소(ax0.line1)는 원본 스크립트가 바뀌면 **조용히** 어긋난다.
색을 바꾸려던 선이 다른 선이 되는 식이다. 그래서 각 artist의 지문을 남기고
로드할 때 대조한다. 불일치는 조용히 넘기지 않고 stale로 표시한다.
"""

from __future__ import annotations

import numpy as np


def _round(v, nd=6):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def of_line(line) -> dict:
    x, y = line.get_xdata(), line.get_ydata()
    n = len(x)
    return {
        "type": "line",
        "n": int(n),
        "head": [_round(x[0]), _round(y[0])] if n else None,
        "tail": [_round(x[-1]), _round(y[-1])] if n else None,
        "label": str(line.get_label()),
    }


def of_collection(coll) -> dict:
    try:
        offs = np.asarray(coll.get_offsets())
        n = int(len(offs))
        bbox = [_round(offs[:, 0].min(), 3), _round(offs[:, 1].min(), 3),
                _round(offs[:, 0].max(), 3), _round(offs[:, 1].max(), 3)] if n else None
    except Exception:
        n, bbox = -1, None
    return {"type": "coll", "n": n, "bbox": bbox, "label": str(coll.get_label())}


def of_patch_group(patches) -> dict:
    total = 0.0
    for p in patches:
        try:
            bb = p.get_extents()
            total += abs(bb.width * bb.height)
        except Exception:
            pass
    return {"type": "patchgroup", "n": len(patches), "area": _round(total, 3)}


def of_text(t) -> dict:
    try:
        x, y = t.get_position()
    except Exception:
        x = y = None
    return {"type": "txt", "label": t.get_text(),
            "xy": [_round(x, 3), _round(y, 3)]}


def of_axes(ax) -> dict:
    try:
        geo = [int(v) for v in ax.get_subplotspec().get_geometry()[:3]]
    except Exception:
        geo = None
    return {
        "type": "axes",
        "geometry": geo,
        "n_lines": len(ax.lines),
        "n_colls": len(ax.collections),
        "n_patches": len(ax.patches),
        # figtune이 추가한 텍스트는 세지 않는다. 지문은 '원본 스크립트가
        # 만든 결과'를 기술해야 한다. 우리 것까지 세면, 저장 시점(라벨 있음)과
        # 로드 직후 대조 시점(아직 적용 전)이 달라 항상 불일치가 난다.
        "n_texts": sum(1 for t in ax.texts
                       if getattr(t, "_figtune_id", None) is None),
    }


def of_figure(fig) -> dict:
    return {"type": "figure", "n_axes": len(fig.axes)}


def matches(a: dict | None, b: dict | None) -> bool:
    """저장된 지문 a와 현재 지문 b가 같은 대상을 가리키는지."""
    if a is None or b is None:
        return True                      # 지문이 없으면 판정 보류
    if a.get("type") != b.get("type"):
        return False
    t = a.get("type")
    if t == "line":
        return (a.get("n") == b.get("n")
                and a.get("head") == b.get("head")
                and a.get("tail") == b.get("tail"))
    if t == "coll":
        return a.get("n") == b.get("n") and a.get("bbox") == b.get("bbox")
    if t == "patchgroup":
        return a.get("n") == b.get("n") and a.get("area") == b.get("area")
    if t == "axes":
        return (a.get("geometry") == b.get("geometry")
                and a.get("n_lines") == b.get("n_lines")
                and a.get("n_colls") == b.get("n_colls")
                and a.get("n_patches") == b.get("n_patches")
                and a.get("n_texts") == b.get("n_texts"))
    if t == "txt":
        return a.get("label") == b.get("label")
    if t == "figure":
        return a.get("n_axes") == b.get("n_axes")
    return a == b


def relabel_candidate(stored: dict, current: dict[str, dict]) -> str | None:
    """어긋난 지문에 대해 라벨 기준 재매칭 후보를 찾는다.

    자동 적용하지 않는다. 사용자에게 제안만 한다.
    """
    label = stored.get("label")
    if not label or label.startswith("_"):
        return None
    hits = [p for p, fp in current.items()
            if fp.get("type") == stored.get("type") and fp.get("label") == label]
    return hits[0] if len(hits) == 1 else None
