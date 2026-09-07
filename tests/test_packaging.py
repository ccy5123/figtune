"""배포 메타데이터 불변식.

버전은 조용히 어긋난다. 패키지를 올리고 CHANGELOG를 잊으면 배포판과 문서가
서로 다른 버전을 말하는데, 릴리스가 끝난 뒤에야 드러난다.

지원 OS도 마찬가지다. CI가 리눅스 단독인 한 다른 OS를 지원한다고 적는 것은
확인하지 않은 것을 확인했다고 말하는 셈이다.
"""

import re
import tomllib
from pathlib import Path

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
