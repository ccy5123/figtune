"""figtune 코어 불변식 테스트.

가장 중요한 두 가지:
  1. 왕복(spec → 코드 → spec)이 값을 잃지 않는다.
  2. 원본 스크립트가 바뀌면 조용히 넘어가지 않는다.
"""

import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import pytest

from figtune.core import parse
from figtune.core.session import Session
from figtune.core.spec import Spec, pyify

EXAMPLE = Path(__file__).parent.parent / "examples" / "plot_fig3.py"

EDITS = [
    ("fig", "size_inches", [7.0, 3.0]),
    ("ax0.line0", "color", "#d62728"),
    ("ax0.line0", "markersize", 5.0),
    ("ax0.line1", "linewidth", 1.4),
    ("ax0.title", "fontsize", 11.0),
    ("ax0.title", "fontweight", "bold"),
    ("ax0", "xlim", [0.0, 48.0]),
    ("ax0", "titlepad", 6.0),
    ("ax0", "xlabelpad", 4.0),
    ("ax0.spine:top", "visible", False),
    ("ax0.spine:left", "position_outward", 5.0),
    ("ax0.xtick.major", "labelsize", 9.0),
    ("ax0.xtick.major", "direction", "in"),
    ("ax0.xtick.major", "locator", {"kind": "multiple", "base": 12.0}),
    ("ax0.grid.y", "visible", True),
    ("ax0.grid.y", "alpha", 0.3),
    ("ax0.legend", "loc", "upper left"),
    ("ax0.legend", "frameon", False),
    ("ax1.ylabel", "text", "Response"),
]


@pytest.fixture
def work(tmp_path):
    dst = tmp_path / "plot_fig3.py"
    shutil.copy(EXAMPLE, dst)
    return dst


@pytest.fixture
def session(work):
    s = Session()
    s.open(work)
    return s


def test_open_builds_tree(session):
    paths = {n.path for n in session.tree.walk()}
    assert {"fig", "ax0", "ax1", "ax0.line0", "ax0.spine:top"} <= paths


def test_roundtrip_preserves_every_override(session):
    for p, n, v in EDITS:
        session.set_prop(p, n, v)
    result = parse.parse_source(session.preview_code())
    assert result.unhandled == []
    for path, over in session.spec.overrides.items():
        for name, value in over.items():
            assert result.spec.get(path, name) == value, f"{path}.{name} 손실"


def test_roundtrip_preserves_user_text(session):
    session.add_panel_labels()
    result = parse.parse_source(session.preview_code())
    assert result.unhandled == []
    got = {(t.id, t.axes, t.text, t.fontweight) for t in result.spec.texts}
    want = {(t.id, t.axes, t.text, t.fontweight) for t in session.spec.texts}
    assert got == want


def test_save_reopen_is_pixel_identical(session, tmp_path):
    for p, n, v in EDITS:
        session.set_prop(p, n, v)
    session.add_panel_labels()
    session.save(install_hook=False)
    a = tmp_path / "a.png"
    session.export(a, dpi=90)

    again = Session()
    rep = again.open(session.script)
    assert not rep.stale
    assert not rep.style_readonly
    assert not rep.apply_failures
    b = tmp_path / "b.png"
    again.export(b, dpi=90)
    assert a.read_bytes() == b.read_bytes()


def test_source_change_is_detected_loudly(session):
    """인덱스가 조용히 밀리는 것이 이 도구의 가장 위험한 실패 모드다."""
    session.set_prop("ax0.line0", "color", "#d62728")
    session.save()

    src = session.script.read_text()
    session.script.write_text(src.replace(
        'axes[0].plot(t, obs, "o", label="Observed", markersize=4)',
        'axes[0].axhline(3.5, color="gray")\n'
        'axes[0].plot(t, obs, "o", label="Observed", markersize=4)'))

    again = Session()
    rep = again.open(session.script)
    assert "ax0.line0" in rep.stale
    assert rep.stale["ax0.line0"]["suggest"] == "ax0.line1"


def test_hook_is_installed_once(session):
    session.set_prop("ax0.line0", "color", "#111111")
    assert session.save(install_hook=True)["hook_installed"] is True
    assert session.save(install_hook=True)["hook_installed"] is False
    assert session.script.read_text().count("apply_style(fig)") == 1


def test_original_plotting_code_is_never_touched(session):
    before = session.script.read_text()
    for p, n, v in EDITS:
        session.set_prop(p, n, v)
    session.save(install_hook=False)
    assert session.script.read_text() == before


def test_unset_props_are_not_emitted(session):
    """원칙 1: 명시하지 않은 값은 코드에 나타나지 않는다."""
    session.set_prop("ax0.line0", "color", "#d62728")
    code = session.preview_code()
    assert "set_color" in code
    assert "set_linestyle" not in code


def test_undo_redo(session):
    session.set_prop("ax0.line0", "color", "#d62728")
    session.set_prop("ax0.line0", "linewidth", 3.0)
    session.history.undo()
    assert session.spec.get("ax0.line0", "linewidth") is None
    session.history.redo()
    assert session.spec.get("ax0.line0", "linewidth") == 3.0


def test_legend_batch_does_not_reset_siblings(session):
    session.set_prop("ax0.legend", "loc", "upper left")
    session.set_prop("ax0.legend", "fontsize", 9.0)
    assert session.spec.get("ax0.legend", "loc") == "upper left"
    assert session.spec.get("ax0.legend", "fontsize") == 9.0


def test_seaborn_legend_keeps_handles(session):
    """seaborn hue 범례는 재생성 시 마커를 잃기 쉽다."""
    before = len(session.fig.axes[1].get_legend().get_texts())
    session.set_prop("ax1.legend", "fontsize", 9.0)
    leg = session.fig.axes[1].get_legend()
    assert len(leg.get_texts()) == before
    handles = getattr(leg, "legend_handles", getattr(leg, "legendHandles", []))
    assert len(handles) == before


def test_hand_edited_style_module_goes_readonly(session):
    session.set_prop("ax0.line0", "color", "#d62728")
    session.save()
    src = session.style_path.read_text()
    session.style_path.write_text(
        src.replace("    axes = fig.axes",
                    "    for _ in range(1):\n        pass\n    axes = fig.axes"))
    again = Session()
    rep = again.open(session.script)
    assert rep.style_readonly


def test_pyify_strips_numpy():
    import numpy as np
    out = pyify({"a": np.float64(1.5), "b": [np.int64(2)], "c": np.array([1, 2])})
    assert out == {"a": 1.5, "b": [2], "c": [1, 2]}
    Spec(overrides={"ax0": {"xlim": [np.float64(0), np.float64(1)]}}).to_dict()


def test_edit_order_does_not_change_result(session, tmp_path):
    """속성 편집 순서가 결과를 바꾸면 안 된다.

    ax.set_title(text, pad=)는 내부에서 폰트 속성을 rcParams 기본값으로
    되돌린다. 그 탓에 '굵게 → 여백' 순서로 편집하면 굵기가 조용히 사라졌다.
    편집 중 화면과 재실행 결과가 갈리는 종류의 버그라 못박아 둔다.
    """
    order_a = [("ax0.title", "fontweight", "bold"),
               ("ax0.title", "fontsize", 13.0),
               ("ax0", "titlepad", 9.0)]
    order_b = list(reversed(order_a))

    outs = []
    for order in (order_a, order_b):
        s = Session()
        s.open(session.script)
        for p, n, v in order:
            s.set_prop(p, n, v)
        outs.append((s.fig.axes[0].title.get_fontweight(),
                     s.fig.axes[0].title.get_fontsize()))

    assert outs[0] == outs[1] == ("bold", 13.0)


def test_title_pad_preserves_font(session):
    session.set_prop("ax0.title", "fontweight", "bold")
    session.set_prop("ax0", "titlepad", 9.0)
    assert session.fig.axes[0].title.get_fontweight() == "bold"


def test_generated_module_actually_runs(session, tmp_path):
    """생성된 코드를 파싱만 하지 말고 실제로 실행해서 같은 그림이 나오는지 본다.

    codegen이 만든 것은 사용자가 앞으로 계속 돌릴 코드다. 문법만 맞고 동작이
    다르면 도구 전체가 거짓말이 된다.
    """
    import subprocess
    import sys

    for p, n, v in EDITS:
        session.set_prop(p, n, v)
    session.add_panel_labels()
    session.save(install_hook=True)

    gui_png = tmp_path / "gui.png"
    session.export(gui_png, dpi=90)

    # 훅이 설치된 스크립트를 별도 프로세스에서 진짜로 실행한다
    script_png = tmp_path / "script.png"
    runner = tmp_path / "_run.py"
    runner.write_text(
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import runpy\n"
        f"ns = runpy.run_path({str(session.script)!r})\n"
        "from matplotlib.figure import Figure\n"
        f"Figure.savefig(ns['fig'], {str(script_png)!r}, dpi=90, bbox_inches='tight')\n",
        encoding="utf-8")
    proc = subprocess.run([sys.executable, str(runner)],
                          capture_output=True, text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr

    assert gui_png.read_bytes() == script_png.read_bytes(), \
        "GUI 렌더와 생성 코드 실행 결과가 다릅니다"


def test_subprocess_mode_yields_editable_figure(work):
    """사용자 인터프리터에서 실행한 Figure도 그대로 편집 가능해야 한다.

    figtune이 얼려진 앱이거나 다른 venv에 있을 때, 스크립트는 사용자 환경에서
    돌아야 import가 해결된다. 그 결과 Figure를 pickle로 건네받는 경로.
    """
    import sys

    s = Session(python=sys.executable)
    s.open(work)
    assert len(s.fig.axes) == 2
    assert len(s.fig.axes[1].collections) >= 1        # seaborn artist 생존
    s.set_prop("ax0.line0", "color", "#c0392b")
    s.set_prop("ax1.legend", "frameon", False)
    assert s.values("ax0.line0")["color"] == "#c0392b"
    leg = s.fig.axes[1].get_legend()
    handles = getattr(leg, "legend_handles", getattr(leg, "legendHandles", []))
    assert len(handles) == 3                          # hue 범례 핸들 보존


def test_provenance_records_data_files(tmp_path):
    """figtune은 데이터를 담지 않는다. 대신 어떤 데이터였는지 지문을 남긴다."""
    (tmp_path / "data.csv").write_text("t,y\n0,1\n1,2\n2,4\n", encoding="utf-8")
    script = tmp_path / "p.py"
    script.write_text(
        "import pandas as pd, matplotlib.pyplot as plt\n"
        "df = pd.read_csv('data.csv')\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot(df.t, df.y)\n", encoding="utf-8")

    s = Session()
    s.open(script)
    s.set_prop("ax0.line0", "color", "#c0392b")
    s.save()

    paths = [Path(d["path"]).name for d in s.spec.data_sources]
    assert "data.csv" in paths
    assert all(d["sha256"] for d in s.spec.data_sources)
    # 스크립트 자신이나 패키지 파일이 섞이면 안 된다
    assert "p.py" not in paths


def test_provenance_detects_changed_data(tmp_path):
    (tmp_path / "data.csv").write_text("t,y\n0,1\n1,2\n", encoding="utf-8")
    script = tmp_path / "p.py"
    script.write_text(
        "import pandas as pd, matplotlib.pyplot as plt\n"
        "df = pd.read_csv('data.csv')\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot(df.t, df.y)\n", encoding="utf-8")

    s = Session()
    s.open(script)
    s.save()
    assert s.data_changes()["changed"] == []

    (tmp_path / "data.csv").write_text("t,y\n0,9\n1,8\n", encoding="utf-8")
    again = Session()
    again.open(script)
    changed = again.data_changes()["changed"]
    assert len(changed) == 1 and Path(changed[0]).name == "data.csv"


def test_data_change_is_distinguished_from_code_change(tmp_path):
    """데이터가 바뀐 것과 코드가 바뀐 것은 다른 경고여야 한다.

    둘을 같은 경고로 묶으면 사용자가 경고를 무시하게 되고, 그러면 진짜
    위험한 경우(인덱스가 밀려 엉뚱한 선에 색이 칠해지는 것)를 놓친다.
    """
    (tmp_path / "data.csv").write_text("t,y\n0,1\n1,2\n", encoding="utf-8")
    script = tmp_path / "p.py"
    script.write_text(
        "import pandas as pd, matplotlib.pyplot as plt\n"
        "df = pd.read_csv('data.csv')\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot(df.t, df.y, label='obs')\n", encoding="utf-8")

    s = Session()
    s.open(script)
    s.set_prop("ax0.line0", "color", "#c0392b")
    s.save()

    # 데이터만 바뀐 경우 → data_changed가 채워진다
    (tmp_path / "data.csv").write_text("t,y\n0,1\n1,2\n2,5\n", encoding="utf-8")
    rep = Session().open(script)
    assert rep.data_changed["changed"], "데이터 변경이 보고되지 않음"

    # 코드만 바뀐 경우 → data_changed는 비어 있어야 한다
    (tmp_path / "data.csv").write_text("t,y\n0,1\n1,2\n", encoding="utf-8")
    s2 = Session()
    s2.open(script)
    s2.save()
    script.write_text(script.read_text().replace(
        "ax.plot(df.t, df.y, label='obs')",
        "ax.axhline(0)\nax.plot(df.t, df.y, label='obs')"), encoding="utf-8")
    rep2 = Session().open(script)
    assert not rep2.data_changed["changed"]
    assert rep2.stale, "코드 변경이 지문으로 잡히지 않음"


# --- 실행 취소 경계 ---------------------------------------------------------

def test_consecutive_edits_to_one_property_collapse():
    """슬라이더를 끄는 동안 수백 칸이 쌓이면 실행 취소가 쓸모없어진다."""
    from figtune.core.history import Command, History

    h = History(lambda *a: None)
    h.push(Command("ax0.title", "fontsize", 10, 11))
    h.push(Command("ax0.title", "fontsize", 11, 12))
    assert len(h) == 1 and h._undo[0].new == 12


def test_seal_starts_a_new_undo_step():
    """끌기 하나가 한 칸이다. 경계가 없으면 두 번의 끌기가 한 칸이 된다."""
    from figtune.core.history import Command, History

    h = History(lambda *a: None)
    h.push(Command("ax0.title", "position", None, [0.6, 1.0]))
    h.seal()
    h.push(Command("ax0.title", "position", [0.6, 1.0], [0.7, 1.0]))
    assert len(h) == 2
    assert [c.new for c in h._undo] == [[0.6, 1.0], [0.7, 1.0]]


def test_seal_does_not_leave_a_dead_step():
    """경계 표식을 스택에 넣으면 실행 취소가 헛걸음을 한다."""
    from figtune.core.history import Command, History

    seen = []
    h = History(lambda p, n, v: seen.append((p, n, v)))
    h.push(Command("ax0.title", "position", None, [0.6, 1.0]))
    h.seal()
    h.push(Command("ax0.title", "position", [0.6, 1.0], [0.7, 1.0]))
    h.undo()
    assert seen == [("ax0.title", "position", [0.6, 1.0])]


def test_seal_only_affects_the_next_push():
    from figtune.core.history import Command, History

    h = History(lambda *a: None)
    h.seal()
    h.push(Command("ax0", "xlim", None, [0, 1]))
    h.push(Command("ax0", "xlim", [0, 1], [0, 2]))
    assert len(h) == 1          # 경계는 한 번만 작동한다


def test_command_extra_is_undone_with_its_parent():
    """범례 끌기는 앵커와 loc을 함께 확정한다. 둘이 한 칸이어야 한다."""
    from figtune.core.history import Command, History

    seen = []
    h = History(lambda p, n, v: seen.append((p, n, v)))
    h.push(Command("ax0.legend", "bbox_to_anchor", None, [0.5, 0.5],
                   extra=[Command("ax0.legend", "loc", None, "upper left")]))
    assert len(h) == 1
    h.undo()
    assert seen == [("ax0.legend", "loc", None),
                    ("ax0.legend", "bbox_to_anchor", None)]


def test_command_extra_is_redone_in_order():
    from figtune.core.history import Command, History

    seen = []
    h = History(lambda p, n, v: seen.append((p, n, v)))
    h.push(Command("ax0.legend", "bbox_to_anchor", None, [0.5, 0.5],
                   extra=[Command("ax0.legend", "loc", None, "upper left")]))
    h.undo()
    seen.clear()
    h.redo()
    # loc이 먼저 정해져야 앵커가 뜻을 갖는다
    assert seen == [("ax0.legend", "loc", "upper left"),
                    ("ax0.legend", "bbox_to_anchor", [0.5, 0.5])]


def test_commands_with_extras_never_collapse():
    """합쳐지면 딸린 변경 하나가 조용히 사라진다."""
    from figtune.core.history import Command, History

    h = History(lambda *a: None)
    for anchor in ([0.4, 0.4], [0.6, 0.6]):
        h.push(Command("ax0.legend", "bbox_to_anchor", None, anchor,
                       extra=[Command("ax0.legend", "loc", None, "upper left")]))
    assert len(h) == 2
