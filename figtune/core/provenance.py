"""데이터 출처 추적.

figtune은 데이터를 들고 있지 않다. 스크립트가 들고 있고 우리는 다시 돌릴
뿐이다. 그래서 Origin처럼 덱이 비대해지지 않고 모델을 다시 돌리면 그림이
따라오지만, 대신 구멍이 하나 생긴다 — **어떤 데이터에서 나온 그림인지 알 수
없다.** 3월 슬라이드와 6월 슬라이드가 똑같이 생겼는데 다른 데이터일 수 있다.

그래서 데이터 자체가 아니라 데이터의 지문을 남긴다. 스크립트가 실행 중 읽은
파일을 audit hook으로 포착하고 해시를 기록한다. 논문 그림의 출처를 나중에
따질 수 있어야 한다.

주의: sys.addaudithook은 한 번 설치하면 제거할 수 없다. 그래서 훅은 한 번만
달고, 기록 여부는 플래그로 켜고 끈다.
"""

from __future__ import annotations

import hashlib
import os
import sys
import sysconfig
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_HASH_BYTES = 256 * 1024 * 1024        # 이보다 크면 해시 생략
_EXCLUDE_SUFFIX = (".py", ".pyc", ".pyd", ".so", ".dll", ".dylib",
                   ".ttf", ".otf", ".afm", ".pfb")
_EXCLUDE_PARTS = ("site-packages", "dist-packages", "__pycache__",
                  ".cache", ".git", ".venv", "node_modules")


@dataclass
class DataSource:
    path: str
    sha256: str | None
    size: int
    mtime: float

    def to_dict(self) -> dict:
        return asdict(self)


class _Recorder:
    """audit hook은 제거 불가라 전역으로 하나만 두고 플래그로 제어한다."""

    def __init__(self):
        self.active = False
        self.paths: list[str] = []
        self._installed = False

    def install(self):
        if self._installed:
            return
        def hook(event, args):
            if event == "open" and self.active:
                try:
                    path, mode = args[0], args[1]
                except (IndexError, TypeError):
                    return
                if isinstance(path, str) and _is_read(mode):
                    self.paths.append(path)
        sys.addaudithook(hook)
        self._installed = True

    def start(self):
        self.install()
        self.paths = []
        self.active = True

    def stop(self) -> list[str]:
        self.active = False
        return list(self.paths)


_recorder = _Recorder()


def _is_read(mode) -> bool:
    m = str(mode or "r")
    return "w" not in m and "a" not in m and "x" not in m


def _system_roots() -> set[str]:
    roots = set()
    for key in ("stdlib", "purelib", "platlib", "data"):
        try:
            roots.add(sysconfig.get_paths()[key])
        except KeyError:
            pass
    roots |= {"/usr", "/etc", "/proc", "/sys", "/dev",
              str(Path.home() / ".cache"), str(Path.home() / ".config")}
    return {r for r in roots if r}


def filter_paths(raw: list[str], roots: list[Path]) -> list[Path]:
    """사용자 데이터로 보이는 것만 남긴다.

    판정 기준은 '스크립트가 있는 트리 안에 있는가'다. 연구 데이터는 코드
    옆에 산다. 시스템 캐시·폰트·패키지 파일은 걸러낸다.
    """
    sysroots = _system_roots()
    roots = [Path(r).resolve() for r in roots]
    out, seen = [], set()

    for p in raw:
        # 스크립트는 데이터를 상대경로로 여는 일이 흔하다. 수집은 실행이 끝난
        # 뒤에 하므로 cwd가 이미 되돌아와 있다. 반드시 스크립트 디렉토리를
        # 기준으로 풀어야 한다.
        cands = [Path(p)] if Path(p).is_absolute() else [r / p for r in roots]
        rp = None
        for c in cands:
            try:
                c = c.resolve()
            except (OSError, ValueError):
                continue
            if c.is_file():
                rp = c
                break
        if rp is None:
            continue
        s = str(rp)
        if s in seen:
            continue
        if rp.suffix.lower() in _EXCLUDE_SUFFIX:
            continue
        if any(part in _EXCLUDE_PARTS for part in rp.parts):
            continue
        if any(s.startswith(r) for r in sysroots):
            continue
        if not any(_under(rp, root) for root in roots):
            continue
        seen.add(s)
        out.append(rp)
    return sorted(out)


def _under(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def digest_file(path: Path, base: Path | None = None) -> DataSource:
    """지문을 만든다.

    경로는 가능하면 base(스크립트 디렉토리) 기준 상대경로로 기록한다.
    절대경로로 남기면 프로젝트를 통째로 옮겼을 때 같은 파일이 '사라짐 +
    추가됨'으로 잡혀 오경보가 난다. 오경보는 경고 전체를 무의미하게 만든다.
    """
    st = path.stat()
    sha = None
    if st.st_size <= MAX_HASH_BYTES:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        sha = h.hexdigest()
    shown = str(path)
    if base is not None:
        try:
            shown = str(path.relative_to(Path(base).resolve()))
        except ValueError:
            pass
    return DataSource(path=shown, sha256=sha,
                      size=st.st_size, mtime=round(st.st_mtime, 3))


def start() -> None:
    _recorder.start()


def collect(roots: list[Path], base: Path | None = None) -> list[DataSource]:
    raw = _recorder.stop()
    base = base or (roots[0] if roots else None)
    return [digest_file(p, base) for p in filter_paths(raw, roots)]


def compare(old: list[dict], new: list[DataSource]) -> dict:
    """기록된 출처와 현재 출처를 비교한다.

    반환: {"changed": [...], "added": [...], "removed": [...]}
    """
    o = {d["path"]: d for d in (old or [])}
    n = {d.path: d for d in new}

    changed = [p for p in o.keys() & n.keys()
               if o[p].get("sha256") != n[p].sha256
               or o[p].get("size") != n[p].size]
    added = set(n.keys() - o.keys())
    removed = set(o.keys() - n.keys())

    # 경로만 달라지고 내용이 같으면 '옮겨진 것'이다. 데이터 변경이 아니다.
    moved = []
    for a in sorted(added):
        sha = n[a].sha256
        if not sha:
            continue
        match = next((r for r in sorted(removed)
                      if o[r].get("sha256") == sha), None)
        if match:
            removed.discard(match)
            added.discard(a)
            moved.append((match, a))

    return {"changed": sorted(changed), "added": sorted(added),
            "removed": sorted(removed), "moved": moved}


# 자식 프로세스(서브프로세스 모드)에 심을 코드
CHILD_SNIPPET = """
import sys as _s
_figtune_opened = []
def _figtune_hook(event, args):
    if event == 'open':
        try:
            p, m = args[0], args[1]
        except Exception:
            return
        if isinstance(p, str):
            mm = str(m or 'r')
            if 'w' not in mm and 'a' not in mm and 'x' not in mm:
                _figtune_opened.append(p)
_s.addaudithook(_figtune_hook)
"""


def collect_from(raw: list[str], roots: list[Path],
                 base: Path | None = None) -> list[DataSource]:
    """이미 수집된 경로 목록으로부터 지문을 만든다 (서브프로세스 모드용)."""
    base = base or (roots[0] if roots else None)
    return [digest_file(p, base) for p in filter_paths(raw, roots)]
