"""배포 메타데이터 불변식.

버전은 조용히 어긋난다. 패키지를 올리고 CHANGELOG를 잊으면 배포판과 문서가
서로 다른 버전을 말하는데, 릴리스가 끝난 뒤에야 드러난다.

지원 OS도 마찬가지다. CI가 리눅스 단독인 한 다른 OS를 지원한다고 적는 것은
확인하지 않은 것을 확인했다고 말하는 셈이다.

바깥으로 나가는 글의 언어도 여기서 지킨다. PyPI는 README를 하나만 싣고
description도 한 줄뿐이라, 그 자리에 한국어가 들어가면 영어권 사용자가 읽을
것이 없다. 한 언어밖에 못 담는 자리는 영어로 둔다.
"""

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:      # Python 3.10에는 없다 — 우리가 지원하는 하한
    import tomli as tomllib

import figtune

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_version_has_a_single_source():
    """pyproject가 값을 적어 두면 한쪽만 고쳐진다."""
    project = PYPROJECT["project"]
    assert "version" not in project, "pyproject에 버전이 직접 적혀 있습니다"
    assert "version" in project["dynamic"]
    assert (PYPROJECT["tool"]["setuptools"]["dynamic"]["version"]["attr"]
            == "figtune.__version__")


def test_changelog_leads_with_the_current_version():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    first = re.search(r"^## \[([^\]]+)\]", text, re.M)
    assert first, "CHANGELOG에 버전 머리글이 없습니다"
    assert first.group(1) == figtune.__version__, (
        f"CHANGELOG 맨 위는 {first.group(1)}, 패키지는 "
        f"{figtune.__version__}입니다")


def test_only_verified_platforms_are_claimed():
    """CI가 도는 OS만 적는다. 다른 OS는 '아마 돌지만 미확인'이 정직하다."""
    os_claims = [c for c in PYPROJECT["project"]["classifiers"]
                 if c.startswith("Operating System")]
    assert os_claims == ["Operating System :: POSIX :: Linux"], os_claims

    ci = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    runners = set(re.findall(r"runs-on:\s*(\S+)", ci))
    assert runners == {"ubuntu-latest"}, (
        f"CI가 {runners}에서 도는데 classifier는 리눅스만 적고 있습니다")


def test_declared_python_versions_match_requires_python():
    lo = PYPROJECT["project"]["requires-python"]
    assert lo == ">=3.10"
    declared = {c.rsplit(" ", 1)[-1]
                for c in PYPROJECT["project"]["classifiers"]
                if c.startswith("Programming Language :: Python :: 3.")}
    assert "3.10" in declared, "requires-python의 하한이 빠졌습니다"


def test_ci_runs_the_lowest_python_we_claim():
    """하한에서 돌려보지 않으면 '지원한다'는 말이 확인되지 않은 주장이다."""
    ci = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    versions = set(re.findall(r'"(3\.\d+)"', ci))
    assert "3.10" in versions, (
        f"requires-python은 3.10부터인데 CI는 {sorted(versions)}만 돕니다")


# --- 바깥으로 나가는 글의 언어 -------------------------------------------

HANGUL = re.compile(r"[가-힣]")


def test_pypi_reads_the_english_readme():
    """PyPI는 readme로 지정한 파일 하나만 싣는다."""
    assert PYPROJECT["project"]["readme"] == "README.md"


def test_the_one_line_description_is_english():
    """pip show와 검색 결과에 실리는 한 줄. 두 언어를 담을 자리가 없다."""
    desc = PYPROJECT["project"]["description"]
    assert not HANGUL.search(desc), f"한국어가 남아 있습니다: {desc}"


# 영어 README에 한국어가 남아도 되는 자리. 전부 한글이 **설명 대상**이라
# 영어로 바꾸면 뜻이 사라지는 곳이다. 여기에 뭔가 추가하기 전에, 그것이 정말
# 번역할 수 없는 것인지 먼저 확인할 것.
ALLOWED_HANGUL = (
    "README.ko.md",          # 언어 전환 링크
    "한국어 / English",       # 언어 메뉴가 각 언어를 제 언어로 적는다는 설명
    "AaBbCc 123 가나다",      # 글꼴 드롭다운의 미리보기 표본
)


def test_the_english_readme_is_english():
    """번역이 반쯤 되다 만 채로 PyPI에 올라가는 것을 막는다."""
    lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    leaks = [f"{i}행: {ln.strip()}" for i, ln in enumerate(lines, 1)
             if HANGUL.search(ln)
             and not any(ok in ln for ok in ALLOWED_HANGUL)]
    assert not leaks, "영어 README에 한국어가 남아 있습니다:\n  " + "\n  ".join(leaks)


def test_both_readmes_point_at_each_other():
    """한쪽만 링크하면 다른 언어판이 있다는 것을 알 길이 없다."""
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    ko = (ROOT / "README.ko.md").read_text(encoding="utf-8")
    assert "README.ko.md" in en, "영어 README에 한국어판 링크가 없습니다"
    assert "README.md" in ko, "한국어 README에 영어판 링크가 없습니다"


def test_the_install_line_is_the_published_one():
    """1.0.0부터는 PyPI에 있다. -e 설치를 안내하면 저장소를 받아야 한다."""
    for name in ("README.md", "README.ko.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert 'pip install "figtune[gui]"' in text, name


def _data_patterns() -> list[str]:
    data = PYPROJECT["tool"]["setuptools"].get("package-data", {})
    return [p for patterns in data.values() for p in patterns]


def test_every_non_python_file_ships():
    """휠은 .py만 담는다. package-data에 적지 않은 파일은 조용히 빠진다.

    README는 FigTune.bas를 애드인 소스라고 안내한다. 그 파일이 휠에 없으면
    pip로 설치한 사람은 안내대로 찾아가도 파일이 없다.
    """
    import fnmatch

    patterns = _data_patterns()
    missing = []
    for path in sorted((ROOT / "figtune").rglob("*")):
        if path.is_dir() or path.suffix == ".py" or "__pycache__" in path.parts:
            continue
        name = path.name
        if not any(fnmatch.fnmatch(name, p) for p in patterns):
            missing.append(str(path.relative_to(ROOT)))
    assert not missing, f"package-data에 없어 휠에서 빠집니다: {missing}"
