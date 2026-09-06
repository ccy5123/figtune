"""테스트 전역 설정.

기존 테스트는 진단 메시지의 한국어 부분 문자열을 단언한다. 언어가 시스템
로케일에서 결정되므로, 고정하지 않으면 영어권 개발자 머신에서만 깨진다.
사용자 설정 파일도 임시 디렉토리로 돌려 실제 홈을 건드리지 않게 한다.
"""

import os

import pytest

from figtune import i18n


@pytest.fixture(autouse=True, scope="session")
def _isolated_user_env(tmp_path_factory):
    home = tmp_path_factory.mktemp("figtune-config")
    os.environ["XDG_CONFIG_HOME"] = str(home)
    os.environ["APPDATA"] = str(home)
    os.environ["FIGTUNE_LANG"] = "ko"
    yield


@pytest.fixture(autouse=True)
def _language_is_korean():
    """테스트끼리 언어 상태가 새지 않도록 매번 원문 언어로 되돌린다."""
    i18n.set_language(i18n.SOURCE_LANG)
    yield
    i18n.set_language(i18n.SOURCE_LANG)
