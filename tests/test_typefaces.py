"""그림에 쓸 수 있는 글꼴 목록.

이 목록이 틀리면 사용자는 원인을 알 수 없다. Qt 목록을 그대로 보여주면
matplotlib이 모르는 글꼴이 섞이고, 고르면 조용히 대체 글꼴로 그려진다.
반대로 matplotlib 캐시가 낡으면 방금 깐 글꼴이 목록에 없다 — 실제로 이
프로젝트를 만들던 머신에서 나눔 글꼴 42개를 깔고도 '한글 글꼴 없음'이
나왔고, 원인은 두 달 전 캐시였다.
"""

import sys
from pathlib import Path

import pytest

from figtune.core import typefaces as T


@pytest.fixture(autouse=True)
def _isolated_default(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))


def _os_release(tmp_path, text):
    p = tmp_path / "os-release"
    p.write_text(text, encoding="utf-8")
    return p


# --- 목록 -----------------------------------------------------------------

def test_lists_something_usable():
    fs = T.available()
    assert fs, "글꼴이 하나도 없으면 matplotlib이 못 그린다"
    assert all(Path(f.path).exists() for f in fs)


def test_names_are_unique_and_sorted():
    """같은 이름이 굵기별로 여러 파일에 나뉘어 있다. 드롭다운에 중복이 뜨면 안 된다."""
    names = [f.name for f in T.available()]
    assert len(names) == len(set(names))
    assert names == sorted(names, key=str.lower)


def test_bundled_fonts_are_marked():
    """matplotlib 번들은 어느 환경에나 있다 — 안전한 기본값으로 쓸 수 있다."""
    bundled = [f for f in T.available() if f.bundled]
    assert any(f.name == "DejaVu Sans" for f in bundled)
    assert all("mpl-data" in f.path for f in bundled)


def test_korean_flag_matches_the_font_file():
    """한글 표시는 파일을 직접 열어 확인한 결과여야 한다. 이름으로 넘겨짚으면
    'NanumGothicCoding' 같은 것을 놓치거나 엉뚱한 것을 넣는다."""
    from matplotlib.ft2font import FT2Font

    for f in T.available()[:25]:
        want = bool(FT2Font(f.path).get_char_index(ord("가")))
        assert f.korean is want, f.name


def test_find_returns_none_for_unknown():
    assert T.find("존재하지 않는 글꼴") is None
    assert T.find("DejaVu Sans") is not None


# --- 캐시 -----------------------------------------------------------------

def test_stale_check_answers_quickly():
    """시작할 때마다 도는 검사다. 느리면 실행이 그만큼 늦어진다."""
    import time

    t0 = time.perf_counter()
    T.cache_is_stale()
    assert (time.perf_counter() - t0) < 1.0


def test_fresh_cache_is_not_reported_stale():
    T.rebuild()
    assert T.cache_is_stale() is False


def test_rebuild_refreshes_the_listing():
    """캐시를 다시 만들면 목록 캐시도 함께 비워야 한다.

    안 비우면 재생성해도 예전 목록이 그대로 나와, 사용자가 글꼴을 깔고
    새로고침을 눌러도 아무 일이 없는 것처럼 보인다.
    """
    before = T.available()
    n = T.rebuild()
    assert n > 0
    assert T.available() is not before      # 캐시가 비워져 다시 만들어졌다
    assert {f.name for f in T.available()} == {f.name for f in before}


def test_ensure_fresh_is_a_noop_when_current():
    T.rebuild()
    assert T.ensure_fresh() is False


# --- 기본 글꼴 -------------------------------------------------------------

def test_default_is_unset_at_first():
    assert T.default_family() is None
    assert T.default_rcparams() == {}


def test_default_roundtrips():
    T.set_default_family("DejaVu Sans")
    assert T.default_family() == "DejaVu Sans"
    assert T.default_rcparams() == {"font.family": "DejaVu Sans"}
    T.set_default_family(None)
    assert T.default_family() is None


def test_unavailable_default_is_ignored():
    """다른 컴퓨터에서 지정한 글꼴이 여기 없을 수 있다. 그대로 rcParams에
    넣으면 matplotlib이 경고를 쏟고 대체 글꼴로 그린다."""
    from figtune import config

    config.set(T.CONFIG_KEY, "있을 리 없는 글꼴")
    assert T.default_family() is None
    assert T.default_rcparams() == {}


# --- 설치 안내 -------------------------------------------------------------

def test_suggestions_cover_korean():
    ko = [s for s in T.SUGGESTIONS if s.korean]
    assert len(ko) >= 2
    assert all(s.url.startswith("https://") for s in T.SUGGESTIONS)


def test_missing_suggestions_excludes_installed():
    have = {f.name for f in T.available()}
    assert all(s.name not in have for s in T.missing_suggestions())


@pytest.mark.skipif(sys.platform != "linux", reason="리눅스 전용 경로")
@pytest.mark.parametrize("release,expected", [
    ("ID=ubuntu\nID_LIKE=debian\n", "apt"),
    ("ID=fedora\n", "dnf"),
    ("ID=arch\n", "pacman"),
])
def test_install_command_matches_the_distro(tmp_path, release, expected):
    sug = T.SUGGESTIONS[0]                      # Noto Sans CJK KR
    cmd = T.install_command(sug, _os_release(tmp_path, release))
    assert expected in cmd and "fc-cache" in cmd


@pytest.mark.skipif(sys.platform != "linux", reason="리눅스 전용 경로")
def test_install_command_is_none_without_a_package(tmp_path):
    """패키지가 없는 글꼴에 엉뚱한 명령을 지어내면 안 된다."""
    dejavu = next(s for s in T.SUGGESTIONS if s.name == "DejaVu Sans")
    assert T.install_command(dejavu, _os_release(tmp_path, "ID=ubuntu\n")) is None


def test_figtune_never_downloads():
    """설치는 사용자가 한다. 도구가 조용히 외부에 접속하면 사내망·오프라인
    환경에서 동작이 예측 불가능해지고 라이선스 책임도 따라온다."""
    src = (Path(T.__file__)).read_text(encoding="utf-8")
    for banned in ("urlopen", "requests", "httpx", "urllib.request", "socket"):
        assert banned not in src, f"{banned} 가 들어왔습니다"


# --- 세션과의 연결 ----------------------------------------------------------

def test_default_font_reaches_the_figure_and_the_spec(tmp_path):
    """rcParams는 이미 만들어진 artist에 소급되지 않는다. 스크립트가 돌기
    전에 얹어야 그림에 실제로 반영된다.

    그리고 spec에 남아야 다른 사람이 같은 코드를 돌렸을 때도 같은 글꼴이
    나온다 — 안 남기면 그림이 사람마다 달라진다.
    """
    import shutil

    import matplotlib
    matplotlib.use("Agg")
    from figtune.core.session import Session

    pick = next(f.name for f in T.available() if f.bundled)
    T.set_default_family(pick)

    script = tmp_path / "p.py"
    shutil.copy(Path(__file__).resolve().parent.parent
                / "examples" / "plot_fig3.py", script)
    s = Session()
    s.open(script)
    try:
        assert s.spec.rcparams.get("font.family") == pick
        assert s.fig.axes[0].title.get_fontfamily()[0] == pick
    finally:
        T.set_default_family(None)


def test_open_repairs_a_stale_font_cache(tmp_path, monkeypatch):
    """캐시가 낡은 채로 열리면 목록에 새 글꼴이 없다."""
    import shutil

    import matplotlib
    matplotlib.use("Agg")
    from figtune.core.session import Session

    calls = []
    monkeypatch.setattr(T, "ensure_fresh", lambda: calls.append(1) or False)
    script = tmp_path / "p.py"
    shutil.copy(Path(__file__).resolve().parent.parent
                / "examples" / "plot_fig3.py", script)
    Session().open(script)
    assert calls, "여는 시점에 캐시를 확인하지 않습니다"


def test_generic_families_are_usable():
    """sans-serif는 matplotlib의 기본값이자 유효한 값이다.
    목록에서 빼면 원래 값이 '설치되지 않음'으로 보여 사용자를 놀라게 한다."""
    for name in T.GENERIC_FAMILIES:
        assert T.is_usable(name), name
    assert not T.is_usable("있을 리 없는 글꼴")
    assert not T.is_usable(None)


def test_generic_can_be_the_default():
    T.set_default_family("serif")
    assert T.default_family() == "serif"
    T.set_default_family(None)
