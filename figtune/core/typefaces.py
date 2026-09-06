"""그림에 쓸 수 있는 글꼴.

Qt가 아는 글꼴과 matplotlib이 아는 글꼴은 다르다. 화면 UI는 Qt가 그리지만
**그림 안의 글자는 matplotlib이 그리므로**, 글꼴 목록은 matplotlib 기준이어야
한다. Qt에는 있는데 matplotlib에는 없는 글꼴을 고르면 조용히 대체 글꼴로
그려지고, 사용자는 왜 안 바뀌는지 알 수 없다.

여기서 가장 중요한 일은 **낡은 캐시를 잡는 것**이다. matplotlib은 글꼴 목록을
파일로 캐시해 두고, 사용자가 글꼴을 새로 깔아도 그 캐시를 갱신하지 않는다.
실제로 이 프로젝트를 만들던 머신에서도 나눔 글꼴 42개를 깐 뒤에 matplotlib은
여전히 '한글 글꼴 없음'이라고 답했다 — 캐시가 두 달 전 것이었다.

Qt를 import하지 않는다.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from matplotlib import font_manager as fm

from .. import config

# 한글을 그릴 수 있는지 재는 표본. 자모가 아니라 완성형이어야 실제 경로를 탄다.
SAMPLE_KO = "가"

CONFIG_KEY = "default_font"

# matplotlib의 총칭 글꼴. 구체적인 글꼴이 아니라 rcParams의 목록을 가리키는
# 별칭이라 어느 환경에나 있고, matplotlib의 기본값도 sans-serif다.
# 목록에서 빼면 원래 값이 '설치되지 않음'으로 보여 사용자를 놀라게 한다.
GENERIC_FAMILIES = ("sans-serif", "serif", "monospace", "cursive", "fantasy")


@dataclass(frozen=True)
class Typeface:
    name: str
    path: str
    bundled: bool          # matplotlib이 들고 다니는 글꼴 — 어느 환경에나 있다
    korean: bool

    def __str__(self) -> str:       # pragma: no cover - 표시용
        return self.name


# --- 캐시 -----------------------------------------------------------------

def cache_is_stale() -> bool:
    """디스크에는 있는데 matplotlib이 모르는 글꼴이 있는가.

    반대(캐시에만 있고 디스크에 없음)는 보지 않는다. 글꼴을 지운 경우인데,
    없는 글꼴을 목록에 하나 더 보여주는 것은 못 보여주는 것보다 덜 나쁘다.
    """
    try:
        on_disk = set(fm.findSystemFonts())
    except Exception:               # pragma: no cover - 환경 의존
        return False
    known = {f.fname for f in fm.fontManager.ttflist}
    return bool(on_disk - known)


def rebuild() -> int:
    """캐시를 다시 만든다. 글꼴 파일 수를 돌려준다."""
    try:
        new = fm._load_fontmanager(try_read_cache=False)
    except Exception:               # pragma: no cover - 사설 API가 바뀌면
        return len(fm.fontManager.ttflist)
    fm.fontManager = new
    available.cache_clear()
    return len(new.ttflist)


def ensure_fresh() -> bool:
    """낡았으면 조용히 다시 만든다. 실제로 다시 만들었으면 True."""
    if not cache_is_stale():
        return False
    rebuild()
    return True


# --- 목록 -----------------------------------------------------------------

def _renders_korean(path: str) -> bool:
    try:
        from matplotlib.ft2font import FT2Font
        return bool(FT2Font(path).get_char_index(ord(SAMPLE_KO)))
    except Exception:
        return False


@lru_cache(maxsize=1)
def available() -> tuple[Typeface, ...]:
    """쓸 수 있는 글꼴. 이름순, 같은 이름은 하나만.

    한글 판정에 191개 파일 기준 55ms가 든다. 목록을 열 때마다 재면 드롭다운이
    체감될 만큼 늦어지므로 한 번만 재고 캐시한다. rebuild()가 비운다.
    """
    mpl_data = str(Path(fm.__file__).parent / "mpl-data")
    by_name: dict[str, Typeface] = {}
    for entry in fm.fontManager.ttflist:
        if entry.name in by_name:
            continue
        by_name[entry.name] = Typeface(
            name=entry.name,
            path=entry.fname,
            bundled=entry.fname.startswith(mpl_data),
            korean=_renders_korean(entry.fname),
        )
    return tuple(sorted(by_name.values(), key=lambda t: t.name.lower()))


def names() -> tuple[str, ...]:
    return tuple(t.name for t in available())


def korean_capable() -> tuple[Typeface, ...]:
    return tuple(t for t in available() if t.korean)


def find(name: str) -> Typeface | None:
    for t in available():
        if t.name == name:
            return t
    return None


def is_usable(name: str | None) -> bool:
    """이 이름을 matplotlib이 알아듣는가. 총칭 글꼴도 포함한다."""
    return bool(name) and (name in GENERIC_FAMILIES or find(name) is not None)


# --- 기본 글꼴 -------------------------------------------------------------

def default_family() -> str | None:
    """사용자가 지정한 기본 글꼴. 지금 쓸 수 없으면 None."""
    name = config.get(CONFIG_KEY)
    return name if is_usable(name) else None


def set_default_family(name: str | None) -> None:
    config.set(CONFIG_KEY, name or None)


def default_rcparams() -> dict:
    """기본 글꼴을 rcParams 형태로. 지정이 없으면 빈 dict.

    spec의 rcparams에 얹으면 생성 코드에도 그대로 나가므로, 다른 사람이
    스크립트를 돌려도 같은 글꼴로 그려진다.
    """
    name = default_family()
    return {"font.family": name} if name else {}


# --- 설치 안내 -------------------------------------------------------------

@dataclass(frozen=True)
class Suggestion:
    name: str
    note: str
    korean: bool
    url: str
    packages: dict          # 배포판 id -> 패키지 이름


# 논문 그림에 흔히 쓰이는 것 위주. 전부 자유 라이선스(OFL/GPL+FE)다.
SUGGESTIONS = (
    Suggestion("Noto Sans CJK KR", "한중일을 모두 덮는 표준 본문용", True,
               "https://github.com/notofonts/noto-cjk",
               {"debian": "fonts-noto-cjk", "ubuntu": "fonts-noto-cjk",
                "fedora": "google-noto-sans-cjk-fonts", "arch": "noto-fonts-cjk",
                "suse": "google-noto-sans-cjk-fonts", "alpine": "font-noto-cjk"}),
    Suggestion("NanumGothic", "한국어 UI·본문에 자연스러운 고딕", True,
               "https://hangeul.naver.com/font",
               {"debian": "fonts-nanum", "ubuntu": "fonts-nanum",
                "fedora": "naver-nanum-gothic-fonts", "arch": "ttf-nanum",
                "suse": "google-noto-sans-cjk-fonts"}),
    Suggestion("NanumMyeongjo", "국문 논문 본문에 쓰는 명조", True,
               "https://hangeul.naver.com/font",
               {"debian": "fonts-nanum-extra", "ubuntu": "fonts-nanum-extra",
                "arch": "ttf-nanum"}),
    Suggestion("Liberation Sans", "Arial 대체. 지표 폭이 같아 배치가 안 바뀐다",
               False, "https://github.com/liberationfonts/liberation-fonts",
               {"debian": "fonts-liberation", "ubuntu": "fonts-liberation",
                "fedora": "liberation-sans-fonts", "arch": "ttf-liberation"}),
    Suggestion("Latin Modern Roman", "LaTeX 본문 글꼴. 논문과 그림을 맞출 때",
               False, "https://www.gust.org.pl/projects/e-foundry/latin-modern",
               {"debian": "fonts-lmodern", "ubuntu": "fonts-lmodern",
                "fedora": "texlive-lm", "arch": "otf-latin-modern"}),
    Suggestion("DejaVu Sans", "matplotlib 기본. 늘 있다", False,
               "https://dejavu-fonts.github.io/", {}),
)


def distro_ids(path: Path = Path("/etc/os-release")) -> list[str]:
    """리눅스 배포판 식별자. 설치 명령을 고르는 데 쓴다."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    ids: list[str] = []
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key in ("ID", "ID_LIKE"):
            ids += value.strip().strip('"').split()
    return ids


def install_command(sug: Suggestion, path: Path = Path("/etc/os-release")) -> str | None:
    """이 환경에서 그 글꼴을 까는 명령. 모르면 None.

    figtune은 글꼴을 직접 내려받지 않는다. 명령만 알려주고 설치는 사용자가
    한다 — 도구가 조용히 외부에 접속하지 않아야 사내망이나 오프라인에서도
    동작이 예측 가능하다.
    """
    if sys.platform != "linux" or not sug.packages:
        return None
    for name in distro_ids(path):
        pkg = sug.packages.get(name)
        if pkg:
            manager = {"fedora": "dnf install -y", "rhel": "dnf install -y",
                       "arch": "pacman -S --noconfirm",
                       "suse": "zypper install -y",
                       "alpine": "apk add"}.get(name, "apt install -y")
            return f"sudo {manager} {pkg} && fc-cache -f"
    pkg = sug.packages.get("debian")
    return f"sudo apt install -y {pkg} && fc-cache -f" if pkg else None


def missing_suggestions() -> tuple[Suggestion, ...]:
    """아직 설치되지 않은 추천 글꼴."""
    have = {t.name for t in available()}
    return tuple(s for s in SUGGESTIONS if s.name not in have)
