"""여러 figure 합치기 테스트.

두 가지 모드가 있고, 무엇을 내놓는지가 서로 다르다는 것이 핵심이다.
  모드 A (montage) — 원본 수정 불필요, SVG 합성물, 하나의 Figure가 아님
  모드 B (subplot) — plot(ax) 노출 필요, 진짜 Figure + 평범한 파이썬 스크립트
"""

import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from figtune.core import montage as M
from figtune.core.montage_build import (MontageSpec, PanelRef, build,
                                        can_use_subplot_mode,
                                        detect_plot_function,
                                        generate_subplot_script)
from figtune.core.session import Session

PLAIN = """import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize={size})
ax.plot([0, 1, 2], [0, 1, 4], 'o-')
ax.set_ylabel({ylab!r}); ax.set_xlabel('Time (h)'); ax.set_title({title!r})
"""

FUNCFORM = """import matplotlib.pyplot as plt

def plot(ax):
    ax.plot([0, 1, 2], [0, 1, 4], 'o-', label={title!r})
    ax.set_ylabel({ylab!r}); ax.set_xlabel('Time (h)'); ax.set_title({title!r})

if __name__ == '__main__':
    fig, ax = plt.subplots()
    plot(ax)
"""


@pytest.fixture
def panels(tmp_path):
    """figure 크기와 y라벨 길이가 일부러 다른 패널들."""
    specs = [((4, 3), "C", "one"), ((5, 3), "Concentration (ug/g)", "two"),
             ((4, 2.5), "y", "three"), ((4.5, 3.2), "Response", "four")]
    names = []
    for i, (size, ylab, title) in enumerate(specs):
        p = tmp_path / f"p{i}.py"
        p.write_text(PLAIN.format(size=size, ylab=ylab, title=title),
                     encoding="utf-8")
        names.append(p.name)
    return tmp_path, names


# --- 모드 A: SVG 합성 -----------------------------------------------------

def test_axes_boxes_align_exactly(panels):
    """단순 타일링은 논문 그림으로 못 쓴다. y라벨 길이가 다르면 그림틀이
    어긋나기 때문이다. axes 상자를 기준으로 맞춰야 한다."""
    base, names = panels
    ms = MontageSpec(rows=2, cols=2,
                     panels=[PanelRef(script=n) for n in names])
    r = build(ms, base_dir=base)

    sizes = {(p["axes_w"], p["axes_h"]) for p in r.placements}
    assert len(sizes) == 1, f"axes 크기가 제각각입니다: {sizes}"

    # 배율 1이어야 글씨가 찌그러지지 않는다
    assert {p["scale"] for p in r.placements} == {1.0}

    for c in range(2):
        xs = {p["axes_x"] for p in r.placements if p["col"] == c}
        assert len(xs) == 1, f"{c}열 왼쪽 모서리 불일치"
    for row in range(2):
        ys = {p["axes_y"] for p in r.placements if p["row"] == row}
        assert len(ys) == 1, f"{row}행 위쪽 모서리 불일치"


def test_panel_labels_never_go_negative(tmp_path):
    """제목이 없는 패널은 위 여백이 거의 없어 라벨이 캔버스 밖으로 나간다."""
    for i in range(2):
        (tmp_path / f"n{i}.py").write_text(
            "import matplotlib.pyplot as plt\n"
            "fig, ax = plt.subplots(figsize=(4,3))\n"
            "ax.plot([0,1],[0,1])\n", encoding="utf-8")
    ms = MontageSpec(rows=1, cols=2,
                     panels=[PanelRef(script=f"n{i}.py") for i in range(2)])
    r = build(ms, base_dir=tmp_path)
    import re
    ys = [float(y) for y in re.findall(r'<text x="[-0-9.]+" y="([-0-9.]+)"', r.svg)]
    assert ys and all(y > 0 for y in ys), f"라벨이 캔버스 밖입니다: {ys}"


def test_ids_are_namespaced_per_panel(panels):
    """id를 격리하지 않으면 뒤 패널 글리프가 앞 패널 것으로 바뀐다."""
    base, names = panels
    ms = MontageSpec(rows=1, cols=2,
                     panels=[PanelRef(script=n) for n in names[:2]])
    r = build(ms, base_dir=base)
    import re
    ids = re.findall(r'id="([^"]+)"', r.svg)
    assert len(ids) == len(set(ids)), "합성 SVG에 중복 id가 있습니다"
    assert any(i.startswith("p0_") for i in ids)
    assert any(i.startswith("p1_") for i in ids)
    # 참조도 함께 바뀌었는지 (끊긴 참조가 없어야 한다)
    refs = set(re.findall(r'href="#([^"]+)"', r.svg)) | \
        set(re.findall(r"url\(#([^)]+)\)", r.svg))
    assert refs <= set(ids), f"끊긴 참조: {refs - set(ids)}"


def test_fit_axes_size_does_not_distort(tmp_path):
    """배율이 아니라 figure를 다시 잡아 axes를 맞춘다."""
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.plot([0, 1], [0, 1])
    ax.set_ylabel("Concentration (ug/g)")
    fig.canvas.draw()

    M.fit_axes_size(fig, 3.0, 2.0)
    w, h = M.axes_size_inches(fig)
    assert abs(w - 3.0) < 1e-6 and abs(h - 2.0) < 1e-6


# --- 모드 B: 진짜 subplot --------------------------------------------------

def test_detects_plot_function(tmp_path):
    plain = tmp_path / "plain.py"
    plain.write_text(PLAIN.format(size=(4, 3), ylab="y", title="t"),
                     encoding="utf-8")
    func = tmp_path / "func.py"
    func.write_text(FUNCFORM.format(ylab="y", title="t"), encoding="utf-8")

    assert detect_plot_function(plain) is None
    assert detect_plot_function(func) == "plot"


def test_subplot_mode_yields_one_real_figure(tmp_path):
    """모드 B의 산출물은 진짜 Figure이자 평범한 파이썬 스크립트다."""
    for i, title in enumerate(("one", "two")):
        (tmp_path / f"f{i}.py").write_text(
            FUNCFORM.format(ylab="C", title=title), encoding="utf-8")

    ms = MontageSpec(rows=1, cols=2,
                     panels=[PanelRef(script=f"f{i}.py") for i in range(2)])
    assert all(can_use_subplot_mode(ms, tmp_path).values())

    merged = generate_subplot_script(ms, tmp_path / "merged.py", base_dir=tmp_path)

    # figtune이 여느 스크립트처럼 열 수 있어야 한다
    s = Session()
    s.open(merged)
    assert len(s.fig.axes) == 2
    assert all(a.figure is s.fig for a in s.fig.axes)
    paths = [n.path for n in s.tree.walk() if n.kind == "line"]
    assert "ax0.line0" in paths and "ax1.line0" in paths

    # 그리고 통째로 편집되고 순수 matplotlib 코드가 나온다
    s.set_prop("ax0.line0", "color", "#c0392b")
    s.save()
    style = (tmp_path / "merged_style.py").read_text(encoding="utf-8")
    assert "set_color('#c0392b')" in style
    assert "figtune" not in style.split('"""')[2]   # 본문에 런타임 의존 없음


def test_subplot_mode_refuses_loudly_when_not_applicable(panels):
    """조용히 모드 A로 떨어지면 어느 산출물을 보고 있는지 알 수 없게 된다."""
    base, names = panels
    ms = MontageSpec(rows=1, cols=2,
                     panels=[PanelRef(script=n) for n in names[:2]])
    with pytest.raises(ValueError) as e:
        generate_subplot_script(ms, base / "m.py", base_dir=base)
    assert "plot(ax)" in str(e.value)


def test_merge_script_runs_without_figtune(tmp_path):
    """생성된 병합 스크립트는 figtune 없이도 실행되어야 한다."""
    import subprocess
    import sys

    for i in range(2):
        (tmp_path / f"f{i}.py").write_text(
            FUNCFORM.format(ylab="C", title=f"p{i}"), encoding="utf-8")
    ms = MontageSpec(rows=1, cols=2,
                     panels=[PanelRef(script=f"f{i}.py") for i in range(2)])
    merged = generate_subplot_script(ms, tmp_path / "merged.py", base_dir=tmp_path)

    runner = tmp_path / "_run.py"
    runner.write_text(
        "import matplotlib\nmatplotlib.use('Agg')\nimport runpy\n"
        f"ns = runpy.run_path({str(merged)!r})\n"
        "assert len(ns['fig'].axes) == 2\n"
        "print('ok')\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(runner)], capture_output=True,
                          text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr


# --- 스크립트가 만든 텍스트 -------------------------------------------------

def test_script_created_text_is_editable(tmp_path):
    """병합 스크립트가 만든 (a)(b) 라벨을 figtune이 볼 수 있어야 한다.

    더 넓게는, 사용자가 ax.text()로 넣은 주석이 편집 대상에서 빠지면
    안 된다.
    """
    for i in range(2):
        (tmp_path / f"f{i}.py").write_text(
            FUNCFORM.format(ylab="C", title=f"p{i}"), encoding="utf-8")
    ms = MontageSpec(rows=1, cols=2,
                     panels=[PanelRef(script=f"f{i}.py") for i in range(2)])
    merged = generate_subplot_script(ms, tmp_path / "merged.py", base_dir=tmp_path)

    s = Session()
    s.open(merged)
    txts = [n for n in s.tree.walk() if n.kind == "txt"]
    assert [n.path for n in txts] == ["ax0.txt0", "ax1.txt0"]
    assert "(a)" in txts[0].label and "(b)" in txts[1].label

    s.set_prop("ax0.txt0", "fontsize", 13.0)
    s.set_prop("ax0.txt0", "color", "#c0392b")
    s.set_prop("ax1.txt0", "position", [-0.2, 1.05])

    from figtune.core import parse
    result = parse.parse_source(s.preview_code())
    assert result.unhandled == []
    assert result.spec.get("ax0.txt0", "fontsize") == 13.0
    assert result.spec.get("ax1.txt0", "position") == [-0.2, 1.05]


def test_script_owned_text_cannot_be_deleted(tmp_path):
    """지워도 재실행하면 되살아난다. 감추려면 visible=False를 쓴다."""
    (tmp_path / "f.py").write_text(FUNCFORM.format(ylab="C", title="p"),
                                   encoding="utf-8")
    (tmp_path / "g.py").write_text(
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot([0,1],[0,1])\n"
        "ax.text(0.5, 0.5, 'note')\n", encoding="utf-8")

    s = Session()
    s.open(tmp_path / "g.py")
    assert s.can_delete("ax0.txt0") is False
    tid = s.add_text(0, "figtune가 넣은 것")
    assert s.can_delete(f"ax0.text:{tid}") is True

    s.set_prop("ax0.txt0", "visible", False)
    assert s.fig.axes[0].texts[0].get_visible() is False


# --- CLI --------------------------------------------------------------------

def test_merge_cli_picks_a_sensible_grid(tmp_path, monkeypatch):
    from figtune.cli import main

    for i in range(4):
        (tmp_path / f"f{i}.py").write_text(
            FUNCFORM.format(ylab="C", title=f"p{i}"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    out = tmp_path / "quad.py"
    assert main(["merge", "f0.py", "f1.py", "f2.py", "f3.py",
                 "-o", str(out)]) == 0
    src = out.read_text(encoding="utf-8")
    assert "'(a)'" in src and "'(d)'" in src

    # 격자 모양은 코드 문자열이 아니라 결과로 확인한다. 리터럴을 단언하면
    # 템플릿을 고칠 때마다 뜻과 상관없이 깨진다.
    s = Session()
    s.open(out)
    assert len(s.fig.axes) == 4                # 4개 → 2×2
    xs = {round(ax.get_position().bounds[0], 3) for ax in s.fig.axes}
    ys = {round(ax.get_position().bounds[1], 3) for ax in s.fig.axes}
    assert len(xs) == 2 and len(ys) == 2


def test_merge_cli_refuses_and_explains(tmp_path, monkeypatch, capsys):
    from figtune.cli import main

    for i in range(2):
        (tmp_path / f"p{i}.py").write_text(
            PLAIN.format(size=(4, 3), ylab="y", title="t"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["merge", "p0.py", "p1.py", "-o", str(tmp_path / "m.py")]) == 1
    err = capsys.readouterr().err
    assert "plot(ax)" in err
    assert "--svg" in err                      # 대안을 알려준다


def test_merge_cli_svg_fallback(tmp_path, monkeypatch):
    from figtune.cli import main

    for i in range(2):
        (tmp_path / f"p{i}.py").write_text(
            PLAIN.format(size=(4, 3), ylab="y", title="t"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    svg = tmp_path / "out.svg"
    assert main(["merge", "p0.py", "p1.py", "-o", str(tmp_path / "m.py"),
                 "--svg", str(svg)]) == 0
    assert svg.exists() and svg.read_text(encoding="utf-8").startswith("<svg")
    assert not (tmp_path / "m.py").exists()    # 모드 B 산출물은 만들지 않았다


# --- 칸 병합(span) ----------------------------------------------------------
#
# 균일 격자만으로는 논문 그림을 못 만든다. 3x2에서 2칸짜리 둘과 1칸짜리 둘
# 같은 조합이 실제로 필요하다.

def _spec(n, **kw):
    return MontageSpec(panels=[PanelRef(script=f"f{i}.py") for i in range(n)],
                       **kw)


def test_unplaced_panels_fill_in_reading_order():
    got = _spec(4, rows=2, cols=2).placements()
    assert got == [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1)]


def test_explicit_span_is_kept():
    ms = _spec(0, rows=2, cols=3)
    ms.panels = [PanelRef(script="a.py", row=0, col=0, colspan=2),
                 PanelRef(script="b.py", row=0, col=2),
                 PanelRef(script="c.py", row=1, col=0),
                 PanelRef(script="d.py", row=1, col=1, colspan=2)]
    assert ms.placements() == [(0, 0, 1, 2), (0, 2, 1, 1),
                               (1, 0, 1, 1), (1, 1, 1, 2)]


def test_unplaced_panels_go_around_a_span():
    """자동 배치는 이미 차지된 칸을 건너뛴다."""
    ms = _spec(0, rows=2, cols=2)
    ms.panels = [PanelRef(script="wide.py", row=0, col=0, colspan=2),
                 PanelRef(script="a.py"), PanelRef(script="b.py")]
    assert ms.placements() == [(0, 0, 1, 2), (1, 0, 1, 1), (1, 1, 1, 1)]


def test_overlapping_cells_are_refused():
    ms = _spec(0, rows=2, cols=2)
    ms.panels = [PanelRef(script="a.py", row=0, col=0, colspan=2),
                 PanelRef(script="b.py", row=0, col=1)]
    with pytest.raises(ValueError, match="겹칩"):
        ms.placements()


def test_a_span_outside_the_grid_is_refused():
    ms = _spec(0, rows=2, cols=2)
    ms.panels = [PanelRef(script="a.py", row=0, col=1, colspan=2)]
    with pytest.raises(ValueError, match="벗어"):
        ms.placements()


def test_too_many_panels_for_the_grid_is_refused():
    with pytest.raises(ValueError, match="칸이 모자"):
        _spec(5, rows=2, cols=2).placements()


def test_placement_survives_the_yaml_roundtrip(tmp_path):
    ms = _spec(0, rows=2, cols=3)
    ms.panels = [PanelRef(script="a.py", row=0, col=0, colspan=2),
                 PanelRef(script="b.py", row=1, col=2, rowspan=1)]
    p = tmp_path / "m.yaml"
    ms.dump(p)
    assert MontageSpec.load(p).placements() == ms.placements()


def test_merge_script_honours_spans(tmp_path):
    """2칸짜리 패널은 실제로 두 칸 너비로 그려져야 한다."""
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.py").write_text(
            FUNCFORM.format(ylab="C", title=name), encoding="utf-8")
    ms = MontageSpec(rows=2, cols=2, panels=[
        PanelRef(script="a.py", row=0, col=0, colspan=2),
        PanelRef(script="b.py", row=1, col=0),
        PanelRef(script="c.py", row=1, col=1)])
    out = generate_subplot_script(ms, tmp_path / "m.py", base_dir=tmp_path)

    s = Session()
    s.open(out)
    boxes = [ax.get_position().bounds for ax in s.fig.axes]
    wide, narrow = boxes[0], boxes[1]
    assert wide[2] > narrow[2] * 1.8, f"넓은 칸이 넓지 않습니다: {boxes}"


def test_merged_figure_is_editable_as_a_whole(tmp_path):
    """병합 결과는 진짜 Figure다 — 열어서 통째로 편집할 수 있어야 한다."""
    for name in ("a", "b"):
        (tmp_path / f"{name}.py").write_text(
            FUNCFORM.format(ylab="C", title=name), encoding="utf-8")
    ms = MontageSpec(rows=1, cols=2, panels=[
        PanelRef(script="a.py", row=0, col=0),
        PanelRef(script="b.py", row=0, col=1)])
    out = generate_subplot_script(ms, tmp_path / "m.py", base_dir=tmp_path)

    s = Session()
    s.open(out)
    s.set_prop("ax0.title", "fontsize", 13.0)
    assert s.fig.axes[0].title.get_fontsize() == 13.0
