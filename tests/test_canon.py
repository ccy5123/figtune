"""정규형 성질 검사.

정규형은 '그렇게 하기로 했다'가 아니라 '검사해서 그렇다'여야 쓸모가 있다.
네 가지 성질을 직접 확인한다.

  (1) 멱등     N(N(x)) = N(x)
  (2) 결정성   같은 내용 → 같은 바이트
  (3) 닫힘     모든 조작의 결과가 다시 정규형
  (4) 왕복     parse(codegen(N(s))) = N(s)
"""

import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import pytest

from figtune.core import canon, parse
from figtune.core.session import Session
from figtune.core.spec import Spec, UserText

EXAMPLE = Path(__file__).parent.parent / "examples" / "plot_fig3.py"

EDITS = [
    ("fig", "size_inches", [7.0, 3.0]),
    ("ax0.line0", "color", "red"),              # 이름 → hex
    ("ax0.line0", "linestyle", "dashed"),       # 별칭 → '--'
    ("ax0.line1", "marker", "None"),            # 빈 마커 표기 통일
    ("ax0.title", "fontweight", "700"),         # 숫자 굵기 → 이름
    ("ax0", "xlim", (0, 48)),                   # 튜플 → 리스트
    ("ax0.spine:top", "visible", False),
    ("ax0.xtick.major", "locator", {"base": 12, "kind": "multiple"}),
    ("ax0.legend", "loc", 2),                   # 정수 코드 → 문자열
    ("ax0.grid.y", "visible", True),
]


@pytest.fixture
def script(tmp_path):
    dst = tmp_path / "plot_fig3.py"
    shutil.copy(EXAMPLE, dst)
    return dst


@pytest.fixture
def edited(script):
    s = Session()
    s.open(script)
    for p, n, v in EDITS:
        s.set_prop(p, n, v)
    s.add_panel_labels()
    return s


# --- (1) 멱등 --------------------------------------------------------------

def test_normalization_is_idempotent(edited):
    once = canon.spec(edited.spec)
    twice = canon.spec(once)
    assert once.to_dict() == twice.to_dict()
    assert canon.is_canonical(once)


def test_messy_spec_becomes_canonical_in_one_pass():
    messy = Spec(
        overrides={
            "ax0.legend": {"loc": 2, "frameon": True},
            "ax0.line0": {"linestyle": "solid", "color": "RED", "alpha": None},
            "fig": {"size_inches": (7, 3)},
            "ax0.empty": {},
            "nonsense.path": {"color": "red"},
        },
        texts=[UserText(id="t009", axes=1, text="(b)"),
               UserText(id="t004", axes=0, text="(a)")],
    )
    n = canon.spec(messy)
    assert canon.is_canonical(n)
    assert n.overrides["ax0.line0"]["linestyle"] == "-"
    assert n.overrides["ax0.line0"]["color"] == "#ff0000"
    assert "alpha" not in n.overrides["ax0.line0"]     # None 제거
    assert "ax0.empty" not in n.overrides              # 빈 dict 제거
    assert "nonsense.path" not in n.overrides          # 해석 불가 제거
    assert n.overrides["ax0.legend"]["loc"] == "upper left"
    assert n.overrides["fig"]["size_inches"] == [7.0, 3.0]
    assert [t.id for t in n.texts] == ["t001", "t002"]  # 연번 재부여
    assert [t.text for t in n.texts] == ["(a)", "(b)"]


# --- (2) 결정성 ------------------------------------------------------------

def test_same_content_serializes_identically(script, tmp_path):
    """입력 순서가 달라도 저장 결과는 같은 바이트여야 한다."""
    outs = []
    for order in (EDITS, list(reversed(EDITS))):
        s = Session()
        s.open(script)
        for p, n, v in order:
            s.set_prop(p, n, v)
        f = tmp_path / f"spec_{len(outs)}.yaml"
        canon.spec(s.spec).dump(f)
        outs.append(f.read_bytes())
    assert outs[0] == outs[1]


def test_alias_spellings_collapse_to_one(script):
    s = Session()
    s.open(script)
    for spelling in ("solid", "-"):
        s.set_prop("ax0.line0", "linestyle", spelling)
        assert s.spec.get("ax0.line0", "linestyle") == "-"
    for spelling in ("red", "#FF0000", "#ff0000"):
        s.set_prop("ax0.line0", "color", spelling)
        assert s.spec.get("ax0.line0", "color") == "#ff0000"
    for spelling in ("None", "none", " "):
        s.set_prop("ax0.line1", "marker", spelling)
        assert s.spec.get("ax0.line1", "marker") == "none"


def test_override_keys_are_sorted_by_application_order(edited):
    n = canon.spec(edited.spec)
    ranks = [canon.path_rank(p) for p in n.overrides]
    assert ranks == sorted(ranks), "override 순서가 정규 순서가 아닙니다"
    for props in n.overrides.values():
        assert list(props) == sorted(props)


def test_ordering_table_is_shared(edited):
    """적용 순서와 정규 정렬 순서가 어긋나면 재현이 깨진다."""
    from figtune.core import apply as ap
    from figtune.core import codegen
    assert ap._ORDER is canon.KIND_ORDER
    assert codegen._ORDER is canon.KIND_ORDER


# --- (3) 닫힘 --------------------------------------------------------------

def test_every_operation_leaves_state_canonical(script):
    """편집 중에는 id 재부여를 뺀 정규형, 경계(open/save)에서는 완전 정규형.

    편집 도중 user text id를 다시 매기면 GUI가 들고 있는 selector가 다른
    텍스트를 가리키게 된다. 그래서 두 단계로 나눠 보장한다.
    """
    s = Session()
    s.open(script)
    assert canon.is_canonical(s.spec), "open 직후가 완전 정규형이 아님"

    for p, n, v in EDITS:
        s.set_prop(p, n, v)
        assert canon.is_canonical(s.spec, ids=False), f"set_prop({p},{n}) 후 비정규"

    s.add_panel_labels()
    assert canon.is_canonical(s.spec, ids=False), "add_panel_labels 후 비정규"

    s.history.undo()
    assert canon.is_canonical(s.spec, ids=False), "undo 후 비정규"
    s.history.redo()
    assert canon.is_canonical(s.spec, ids=False), "redo 후 비정규"

    s.reset_prop("ax0.line0", "color")
    assert canon.is_canonical(s.spec, ids=False), "reset_prop 후 비정규"

    s.save()
    assert canon.is_canonical(s.spec), "save 후 완전 정규형이 아님"
    assert canon.is_canonical(Spec.load(s.spec_path)), "저장된 파일이 비정규"


def test_deleting_text_mid_session_does_not_shift_ids(script):
    """편집 중 id가 밀리면 GUI가 들고 있는 selector가 무효가 된다."""
    s = Session()
    s.open(script)
    a = s.add_text(0, "첫째")
    b = s.add_text(0, "둘째")
    s.set_prop(f"ax0.text:{b}", "fontsize", 12.0)
    s.delete_text(a)
    assert s.spec.text_by_id(b) is not None, f"{b}가 사라졌습니다"
    # user text 속성은 overrides가 아니라 UserText 객체에 산다
    assert s.spec.text_by_id(b).fontsize == 12.0
    assert s.spec.text_by_id(b).text == "둘째"

    # 경계에서는 연번으로 정리된다
    s.save()
    assert [t.id for t in s.spec.texts] == ["t001"]


def test_reopened_state_is_canonical(edited):
    edited.save()
    again = Session()
    again.open(edited.script)
    assert canon.is_canonical(again.spec)


# --- (4) 왕복 --------------------------------------------------------------

def test_codegen_parse_roundtrip_is_exact_on_canonical_form(edited):
    n = canon.spec(edited.spec)
    result = parse.parse_source(edited.preview_code())
    assert result.unhandled == []
    assert result.spec.overrides == n.overrides
    assert ([(t.id, t.text, t.axes) for t in result.spec.texts]
            == [(t.id, t.text, t.axes) for t in n.texts])


def test_codegen_output_is_byte_stable(edited):
    """같은 spec은 항상 같은 코드를 낸다."""
    a = edited.preview_code()
    edited.normalize()
    b = edited.preview_code()
    assert a == b


def test_diff_reports_only_real_changes(script):
    a = Session()
    a.open(script)
    a.set_prop("ax0.line0", "linestyle", "solid")
    b = Session()
    b.open(script)
    b.set_prop("ax0.line0", "linestyle", "-")
    assert canon.diff(a.spec, b.spec) == []

    b.set_prop("ax0.line0", "linewidth", 2.0)
    assert any("linewidth" in d for d in canon.diff(a.spec, b.spec))


def test_group_headers_describe_the_whole_group(edited):
    """`# --- ax0.line0 ---` 아래에 line1이 들어가면 주석이 거짓말이 된다."""
    code = edited.preview_code()
    body = code.split("def apply_style(fig):")[1]
    headers = [l.strip() for l in body.splitlines() if l.strip().startswith("# ---")]
    assert any("ax0.lines" in h for h in headers)
    assert not any("line0" in h or "line1" in h for h in headers)
