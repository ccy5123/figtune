"""메시지 카탈로그.

msgid는 한국어 원문 그 자체다. 별도의 키를 두지 않으므로 props.REGISTRY의
라벨 100여 개를 손대지 않아도 되고, 카탈로그에 없는 문장은 원문이 그대로
나오므로 번역이 빠져도 화면이 비지 않는다. 누락은 tests/test_i18n.py가 잡는다.

core도 이 모듈을 쓴다. 그래서 여기에 Qt나 matplotlib을 import하면 안 된다.

생성 산출물(*_style.py 헤더, 병합 스크립트)은 이 모듈을 거치지 않는다. 같은
spec이 사용자 언어에 따라 다른 바이트로 나오면 결정성이 깨지기 때문이다.
"""

from __future__ import annotations

import os

from .. import config

SOURCE_LANG = "ko"
LANGUAGES = ("ko", "en")
ENV_VAR = "FIGTUNE_LANG"

_LANG = SOURCE_LANG
_CATALOGS: dict[str, dict[str, str]] = {}


# --- 카탈로그 -------------------------------------------------------------


def _catalog(lang: str) -> dict[str, str]:
    if lang == SOURCE_LANG:
        return {}
    if lang not in _CATALOGS:
        if lang == "en":
            from . import en
            _CATALOGS[lang] = en.MESSAGES
        else:
            _CATALOGS[lang] = {}
    return _CATALOGS[lang]


def t(msg: str, **kw) -> str:
    """한국어 원문을 현재 언어로 옮긴다.

    자리표시자는 이름 있는 것만 쓴다. 언어마다 어순이 달라지므로 위치 기반
    자리표시자는 번역문에서 순서를 바꿀 수 없다.
    """
    out = _catalog(_LANG).get(msg, msg)
    return out.format(**kw) if kw else out


# --- 현재 언어 ------------------------------------------------------------


def get_language() -> str:
    return _LANG


def set_language(lang: str) -> str:
    """현재 언어를 바꾸고 실제로 적용된 언어를 돌려준다."""
    global _LANG
    _LANG = lang if lang in LANGUAGES else SOURCE_LANG
    return _LANG


# --- 결정 순서 ------------------------------------------------------------


def save_language(lang: str | None) -> None:
    """언어 선택을 저장한다. None이면 '시스템 따름'으로 되돌린다."""
    config.set("lang", lang)


def saved_language() -> str | None:
    lang = config.get("lang")
    return lang if lang in LANGUAGES else None


def system_language() -> str | None:
    """환경변수와 로케일에서 언어를 읽는다.

    LANGUAGE는 콜론으로 구분된 우선순위 목록이라 앞에서부터 본다.
    """
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        raw = os.environ.get(var)
        if not raw:
            continue
        for token in raw.split(":"):
            code = token.split(".")[0].split("_")[0].strip().lower()
            if code in LANGUAGES:
                return code
    try:
        import locale
        code = (locale.getlocale()[0] or "").split("_")[0].lower()
    except (ValueError, TypeError):
        return None
    return code if code in LANGUAGES else None


def resolve_language(explicit: str | None = None) -> str:
    """--lang > FIGTUNE_LANG > 설정파일 > 시스템 로케일 > 원문 언어."""
    if explicit and explicit != "auto":
        if explicit in LANGUAGES:
            return explicit
    env = (os.environ.get(ENV_VAR) or "").strip().lower()
    if env in LANGUAGES:
        return env
    return saved_language() or system_language() or SOURCE_LANG


def init(explicit: str | None = None) -> str:
    """진입점에서 한 번 호출한다."""
    return set_language(resolve_language(explicit))
