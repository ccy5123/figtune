"""사용자 설정 파일.

세션을 넘어 기억해야 하는 것만 담는다 (언어 선택, 한 번만 띄우는 안내 등).
그림이나 spec에 영향을 주는 값은 절대 넣지 않는다 — 그런 값이 여기 들어가면
같은 spec이 사람마다 다른 그림을 내게 되고, 재현 가능성이 무너진다.

설정을 못 읽거나 못 써도 동작은 계속되어야 한다. 설정은 편의일 뿐이다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def path() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "figtune" / "config.json"


def load() -> dict:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def get(key: str, default=None):
    return load().get(key, default)


def set(key: str, value) -> None:      # noqa: A001 - 설정 키 접근자라 이 이름이 맞다
    """value가 None이면 키를 지운다 (= 기본값으로 되돌림)."""
    cfg = load()
    if value is None:
        cfg.pop(key, None)
    else:
        cfg[key] = value
    p = path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    except OSError:
        pass
