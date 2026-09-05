"""Spec — 단일 원본.

원칙:
  1. null / 부재 = 건드리지 않음. 명시된 키만 override 코드로 생성된다.
     원본 스크립트가 설정한 값이 GUI를 열었다는 이유만으로 덮이지 않는다.
  2. 개별 artist override가 rcparams보다 우선한다.
  3. 모든 값은 YAML 리터럴. 표현식 없음.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml

SPEC_VERSION = "0.1"


@dataclass
class UserText:
    """figtune이 새로 추가한 텍스트. 원본 코드에는 존재하지 않는다."""
    id: str
    axes: int
    text: str = ""
    position: list[float] = field(default_factory=lambda: [0.5, 0.5])
    coords: str = "axes"          # data | axes | figure
    fontsize: float | None = None
    color: str | None = None
    fontfamily: str | None = None
    fontweight: str | None = None
    fontstyle: str | None = None
    rotation: float | None = None
    horizontalalignment: str = "left"
    verticalalignment: str = "bottom"
    zorder: float | None = None

    def style(self) -> dict:
        keys = ("fontsize", "color", "fontfamily", "fontweight", "fontstyle",
                "rotation", "horizontalalignment", "verticalalignment", "zorder")
        return {k: getattr(self, k) for k in keys if getattr(self, k) is not None}


@dataclass
class Spec:
    version: str = SPEC_VERSION
    script: str = ""
    style_module: str = ""
    rcparams: dict[str, Any] = field(default_factory=dict)
    # selector 경로 -> {prop: value}
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    # selector 경로 -> fingerprint dict
    fingerprints: dict[str, dict] = field(default_factory=dict)
    texts: list[UserText] = field(default_factory=list)
    # 스크립트가 읽은 데이터 파일의 지문. 데이터 자체는 담지 않는다.
    data_sources: list[dict] = field(default_factory=list)

    # --- override 조작 ---------------------------------------------------

    def set(self, path: str, name: str, value: Any) -> None:
        if value is None:
            self.unset(path, name)
            return
        self.overrides.setdefault(path, {})[name] = value

    def unset(self, path: str, name: str) -> None:
        d = self.overrides.get(path)
        if not d:
            return
        d.pop(name, None)
        if not d:
            self.overrides.pop(path, None)

    def get(self, path: str, name: str, default=None) -> Any:
        return self.overrides.get(path, {}).get(name, default)

    def of(self, path: str) -> dict:
        return self.overrides.get(path, {})

    # --- user text -------------------------------------------------------

    def new_text_id(self) -> str:
        n = 1
        used = {t.id for t in self.texts}
        while f"t{n:03d}" in used:
            n += 1
        return f"t{n:03d}"

    def text_by_id(self, tid: str) -> UserText | None:
        for t in self.texts:
            if t.id == tid:
                return t
        return None

    def remove_text(self, tid: str) -> None:
        self.texts = [t for t in self.texts if t.id != tid]
        for path in list(self.overrides):
            if path.endswith(f".text:{tid}"):
                self.overrides.pop(path)

    # --- 직렬화 ----------------------------------------------------------

    def to_dict(self) -> dict:
        return pyify({
            "figtune_version": self.version,
            "source": {"script": self.script, "style_module": self.style_module},
            "rcparams": self.rcparams,
            "overrides": self.overrides,
            "fingerprints": self.fingerprints,
            "texts": [asdict(t) for t in self.texts],
            "data_sources": self.data_sources,
        })

    @classmethod
    def from_dict(cls, d: dict) -> "Spec":
        src = d.get("source") or {}
        return cls(
            version=d.get("figtune_version", SPEC_VERSION),
            script=src.get("script", ""),
            style_module=src.get("style_module", ""),
            rcparams=d.get("rcparams") or {},
            overrides=d.get("overrides") or {},
            fingerprints=d.get("fingerprints") or {},
            texts=[UserText(**t) for t in (d.get("texts") or [])],
            data_sources=d.get("data_sources") or [],
        )

    def dump(self, path: str | Path) -> None:
        Path(path).write_text(
            yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True),
            encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Spec":
        return cls.from_dict(
            yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})


def pyify(obj: Any) -> Any:
    """numpy 스칼라/배열을 순수 Python 값으로 낮춘다.

    matplotlib getter는 np.float64 등을 흔히 돌려준다. YAML은 그것을 표현하지
    못하므로 직렬화 경계에서 한 번 정화한다. 값이 들어오는 모든 경로에
    방어 코드를 흩뿌리는 것보다 여기 한 곳을 지키는 편이 낫다.
    """
    if isinstance(obj, dict):
        return {str(k): pyify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [pyify(v) for v in obj]
    if isinstance(obj, (str, bool, int, float)) or obj is None:
        return obj
    if hasattr(obj, "item") and getattr(obj, "ndim", None) == 0:
        return obj.item()
    if hasattr(obj, "tolist"):
        return pyify(obj.tolist())
    return obj


def digest(obj: Any) -> str:
    return hashlib.sha256(repr(obj).encode()).hexdigest()[:16]
