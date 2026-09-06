"""번역 카탈로그 불변식.

번역은 조용히 썩는다. 문장을 고치고 카탈로그를 잊으면 그 줄만 원문으로
남고, 아무도 알아채지 못한다. 그래서 다음 넷을 기계로 못박는다.

  1. 소스의 모든 msgid가 카탈로그에 있다 (누락 없음)
  2. 카탈로그에 소스에 없는 키가 없다 (쓰레기 없음)
  3. 자리표시자가 번역을 건너도 살아남는다
  4. 사용자에게 보이는 한국어가 _t() 밖에 남아 있지 않다

그리고 가장 중요한 하나 — 생성 산출물은 언어와 무관하게 같은 바이트여야
한다. 여기가 깨지면 같은 spec이 사람마다 다른 파일을 내고 git이 요동친다.
"""

import ast
import os
import re
import string
from pathlib import Path

import pytest

from figtune import config, i18n
from figtune.core import props as P
from figtune.core import selector as sel
from figtune.core import typefaces
from figtune.i18n import en

PKG = Path(__file__).resolve().parent.parent / "figtune"
CATALOG_FILE = PKG / "i18n" / "en.py"
HANGUL = re.compile(r"[가-힣]")


# --- 소스 수집 -------------------------------------------------------------

def _sources():
    return [p for p in sorted(PKG.rglob("*.py")) if p != CATALOG_FILE]


def _translated_ids(tree):
    """_t()/t()의 첫 인자로 들어간 문자열 상수의 id 집합."""
    ids = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name not in ("t", "_t"):
            continue
        if node.args and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str):
            ids[id(node.args[0])] = node.args[0].value
    return ids


def _docstring_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            if ast.get_docstring(node) is not None and node.body:
                ids.add(id(node.body[0].value))
    return ids


def source_msgids() -> dict[str, str]:
    """msgid -> 처음 나온 위치."""
    found = {}
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for msg in _translated_ids(tree).values():
            found.setdefault(msg, f"{path.name}")
    # 인스펙터가 prop.label을 _t()에 넘기므로 레지스트리도 msgid 원천이다
    for kind, props in P.REGISTRY.items():
        for prop in props:
            found.setdefault(prop.label, f"props.REGISTRY[{kind!r}]")
    # 글꼴 추천 설명도 표시 시점에 번역된다
    for sug in typefaces.SUGGESTIONS:
        found.setdefault(sug.note, f"typefaces.SUGGESTIONS[{sug.name!r}]")
    # selector 종류 이름(대화상자 탭)도 마찬가지
    for kind, label in sel.KIND_LABELS.items():
        found.setdefault(label, f"selector.KIND_LABELS[{kind!r}]")
    return found


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


# --- 1. 누락 없음 -----------------------------------------------------------

def test_every_message_is_translated():
    missing = sorted(m for m in source_msgids() if m not in en.MESSAGES)
    assert not missing, (
        f"en.py에 없는 msgid {len(missing)}개:\n  "
        + "\n  ".join(repr(m) for m in missing[:20]))


# --- 2. 쓰레기 없음 ---------------------------------------------------------

def test_catalog_has_no_stale_entries():
    known = source_msgids()
    stale = sorted(k for k in en.MESSAGES if k not in known)
    assert not stale, (
        f"소스에 없는 카탈로그 키 {len(stale)}개 (문장이 바뀌었는데 "
        f"카탈로그를 안 고쳤을 수 있습니다):\n  "
        + "\n  ".join(repr(k) for k in stale[:20]))


# --- 3. 자리표시자 보존 ------------------------------------------------------

def test_placeholders_survive_translation():
    """번역문은 자리표시자 순서를 바꿔도 되지만 잃거나 만들어내면 안 된다."""
    bad = []
    for src, dst in en.MESSAGES.items():
        if _fields(src) != _fields(dst):
            bad.append((src, _fields(src), _fields(dst)))
    assert not bad, "\n".join(
        f"{s!r}: 원문 {a} vs 번역 {b}" for s, a, b in bad)


def test_positional_placeholders_are_not_used():
    """{0}/{} 는 어순이 바뀌는 언어에서 재배치가 불가능하다."""
    offenders = [m for m in source_msgids()
                 if any(f.isdigit() or f == "" for f in _fields(m))]
    assert not offenders, offenders


# --- 4. _t() 밖에 남은 한국어 없음 -------------------------------------------

# 메시지가 아니라서 번역 대상이 아닌 한국어. 늘어나면 그때마다 근거를 적을 것.
ALLOWED_KOREAN = {
    "가",        # fonts.SAMPLE — 렌더 가능 여부를 재는 표본 글자
    "한국어",     # 언어 메뉴 항목. 읽을 수 없는 언어에 갇혔을 때의 탈출구다
    # 글꼴 미리보기 표본. 번역 대상이 아니라 '이 글꼴이 한글을 그리는가'를
    # 눈으로 확인시키는 그림이다 — 영어 UI에서도 그대로 보여야 뜻이 있다.
    "AaBbCc 123 가나다",
}


def test_no_user_facing_korean_outside_translation():
    """주석·docstring이 아니면서 _t()를 거치지 않는 한국어 문자열은 없어야 한다.

    props.REGISTRY의 라벨은 인스펙터가 _t(prop.label)로 넘기므로 예외다 —
    누락 여부는 test_every_message_is_translated가 따로 본다.

    생성 산출물(*_style.py 헤더, 병합 스크립트)은 영어로 고정했으므로 여기서
    예외가 필요 없다. ALLOWED_KOREAN에 뭔가 넣기 전에, 그 문자열이 정말
    사용자에게 메시지로 보이지 않는지 먼저 확인할 것.
    """
    registry_labels = {p.label for props in P.REGISTRY.values() for p in props}
    registry_labels |= {s.note for s in typefaces.SUGGESTIONS}
    registry_labels |= set(sel.KIND_LABELS.values())
    leaks = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = set(_translated_ids(tree)) | _docstring_ids(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and HANGUL.search(node.value)):
                continue
            if id(node) in skip or node.value in registry_labels \
                    or node.value in ALLOWED_KOREAN:
                continue
            leaks.append(f"{path.name}:{node.lineno}  {node.value[:50]!r}")
    assert not leaks, "번역되지 않은 문자열:\n  " + "\n  ".join(leaks)


# --- 폴백과 포맷 ------------------------------------------------------------

def test_missing_translation_falls_back_to_source():
    i18n.set_language("en")
    assert i18n.t("카탈로그에 없는 문장") == "카탈로그에 없는 문장"


def test_translation_applies_and_formats():
    i18n.set_language("en")
    assert i18n.t("파일 없음: {path}", path="a.py") == "no such file: a.py"
    i18n.set_language("ko")
    assert i18n.t("파일 없음: {path}", path="a.py") == "파일 없음: a.py"


def test_source_language_needs_no_catalog():
    i18n.set_language("ko")
    assert i18n.t("크기 (in)") == "크기 (in)"


def test_unknown_language_falls_back_to_source():
    assert i18n.set_language("zz") == i18n.SOURCE_LANG


# --- 언어 결정 순서 ---------------------------------------------------------

def test_explicit_beats_environment(monkeypatch):
    monkeypatch.setenv("FIGTUNE_LANG", "ko")
    assert i18n.resolve_language("en") == "en"


def test_auto_defers_to_environment(monkeypatch):
    monkeypatch.setenv("FIGTUNE_LANG", "en")
    assert i18n.resolve_language("auto") == "en"
    assert i18n.resolve_language(None) == "en"


def test_environment_beats_saved_setting(monkeypatch):
    config.set("lang", "ko")
    monkeypatch.setenv("FIGTUNE_LANG", "en")
    assert i18n.resolve_language() == "en"
    config.set("lang", None)


def test_saved_setting_beats_locale(monkeypatch):
    monkeypatch.delenv("FIGTUNE_LANG", raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    config.set("lang", "ko")
    try:
        assert i18n.resolve_language() == "ko"
    finally:
        config.set("lang", None)


def test_locale_is_used_when_nothing_is_configured(monkeypatch):
    monkeypatch.delenv("FIGTUNE_LANG", raising=False)
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n.resolve_language() == "en"


def test_unknown_locale_falls_back_to_source(monkeypatch):
    import locale

    monkeypatch.delenv("FIGTUNE_LANG", raising=False)
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    # getlocale()은 프로세스 시작 시점의 로케일을 들고 있어 환경변수를 지워도
    # 남는다. 그대로 두면 러너의 로케일에 따라 결과가 달라진다.
    monkeypatch.setattr(locale, "getlocale", lambda *a: (None, None))
    assert i18n.resolve_language() == i18n.SOURCE_LANG


# --- 설정 파일 --------------------------------------------------------------

def test_config_roundtrip_and_clear():
    config.set("lang", "en")
    assert config.get("lang") == "en"
    config.set("lang", None)
    assert config.get("lang") is None


def test_config_survives_a_corrupt_file():
    p = config.path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json", encoding="utf-8")
    assert config.load() == {}
    config.set("lang", "en")        # 깨진 파일 위에도 다시 쓸 수 있어야 한다
    assert config.get("lang") == "en"
    config.set("lang", None)


# --- 생성 산출물은 언어와 무관하다 (가장 중요) --------------------------------

def _style_source(tmp_path, lang):
    """언어만 다르고 나머지는 완전히 같은 조건으로 스타일 모듈을 만든다."""
    import matplotlib
    matplotlib.use("Agg")
    from figtune.core.session import Session

    # 파일 이름이 생성 헤더에 들어가므로 이름은 같게, 디렉토리만 나눈다
    workdir = tmp_path / lang
    workdir.mkdir()
    script = workdir / "panel.py"
    script.write_text(
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot([0, 1], [0, 1])\n"
        "ax.set_title('t')\n", encoding="utf-8")
    i18n.set_language(lang)
    s = Session()
    s.open(script)
    s.set_prop("ax0.line0", "color", "#ff0000")
    s.add_text(0, "hello")
    return s.preview_code()


def test_generated_code_does_not_depend_on_language(tmp_path):
    ko = _style_source(tmp_path, "ko")
    en_ = _style_source(tmp_path, "en")
    # 헤더의 절대경로만 언어별 디렉토리 때문에 다르다
    strip = lambda s: "\n".join(  # noqa: E731
        ln for ln in s.splitlines() if "source script" not in ln)
    assert strip(ko) == strip(en_)
    assert not HANGUL.search(en_), "생성 코드에 한국어가 남아 있습니다"
    assert not HANGUL.search(ko), "생성 코드는 언어와 무관하게 영어여야 합니다"


def test_merge_template_is_language_independent():
    from figtune.core.montage_build import MERGE_TEMPLATE
    assert not HANGUL.search(MERGE_TEMPLATE)


@pytest.mark.parametrize("lang", ["ko", "en"])
def test_cli_help_runs_in_both_languages(lang, capsys):
    from figtune.cli import main
    with pytest.raises(SystemExit):
        main(["--lang", lang, "--help"])
    out = capsys.readouterr().out
    assert "figtune" in out
    if lang == "en":
        assert not HANGUL.search(out), out
