"""seaborn FacetGrid 등 figure 수준 구조를 쓰는 그림.

여기서 드러난 문제는 FacetGrid만의 것이 아니다. figure에 붙은 텍스트와
범례는 어떤 스크립트에서든 나올 수 있고, 지금까지 통째로 빠져 있었다.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import pytest

from figtune.core import parse
from figtune.core.session import Session

FACET = """import seaborn as sns, numpy as np, pandas as pd
r = np.random.default_rng(0)
df = pd.DataFrame({'x': r.random(120), 'y': r.random(120),
                   'g': np.repeat(list('abcd'), 30),
                   'h': np.tile(list('XY'), 60)})
g = sns.relplot(data=df, x='x', y='y', col='g', hue='h', col_wrap=2)
g.figure.suptitle('Overview')
fig = g.figure
"""

SUPTITLE = """import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot([0, 1], [0, 1])
fig.suptitle('Title')
fig.text(0.5, 0.02, 'footnote')
"""


@pytest.fixture
def facet(tmp_path):
    p = tmp_path / "fg.py"
    p.write_text(FACET, encoding="utf-8")
    s = Session()
    s.open(p)
    return s


def test_facetgrid_panels_are_editable(facet):
    assert len(facet.fig.axes) == 4
    assert [a.get_title() for a in facet.fig.axes] == [
        "g = a", "g = b", "g = c", "g = d"]
    facet.set_prop("ax0.spine:top", "visible", False)
    assert facet.fig.axes[0].spines["top"].get_visible() is False


def test_override_never_manufactures_a_missing_legend(facet):
    """FacetGrid 범례는 figure에 붙는다. 패널에 override를 걸었다고
    없던 범례를 만들면, 사용자가 요청하지 않은 그림 변경이 된다."""
    assert facet.fig.axes[0].get_legend() is None
    facet.set_prop("ax0.legend", "frameon", False)
    assert facet.fig.axes[0].get_legend() is None, "없던 범례가 생겼습니다"


def test_explicit_visible_true_may_create_one(tmp_path):
    """다만 사용자가 명시적으로 켜면 만들어야 한다."""
    p = tmp_path / "p.py"
    p.write_text("import matplotlib.pyplot as plt\n"
                 "fig, ax = plt.subplots()\n"
                 "ax.plot([0,1],[0,1], label='A')\n", encoding="utf-8")
    s = Session()
    s.open(p)
    assert s.fig.axes[0].get_legend() is None
    s.set_prop("ax0.legend", "visible", True)
    assert s.fig.axes[0].get_legend() is not None


def test_figure_level_texts_are_editable(tmp_path):
    p = tmp_path / "p.py"
    p.write_text(SUPTITLE, encoding="utf-8")
    s = Session()
    s.open(p)

    paths = [n.path for n in s.tree.walk() if n.kind == "figtext"]
    assert "fig.suptitle" in paths
    assert any(x.startswith("fig.txt") for x in paths)

    s.set_prop("fig.suptitle", "fontsize", 13.0)
    s.set_prop("fig.suptitle", "fontweight", "bold")
    assert s.fig._suptitle.get_fontsize() == 13.0

    result = parse.parse_source(s.preview_code())
    assert result.unhandled == []
    assert result.spec.of("fig.suptitle") == {"fontsize": 13.0,
                                              "fontweight": "bold"}


def test_facet_suptitle_roundtrips(facet):
    facet.set_prop("fig.suptitle", "color", "#c0392b")
    result = parse.parse_source(facet.preview_code())
    assert result.unhandled == []
    assert result.spec.get("fig.suptitle", "color") == "#c0392b"


def test_facetgrid_cannot_be_normalized_and_says_why(tmp_path):
    from figtune.core import normalize as N
    rep = N.analyze(FACET)
    assert not rep.ok
    assert "plt.subplots()" in rep.reasons[0]


# --- figure 수준 범례 -------------------------------------------------------

def test_figure_legend_is_editable_in_place(facet):
    """FacetGrid 범례는 재생성하면 seaborn이 단 핸들을 잃는다.
    있는 Legend 객체를 제자리에서 고쳐야 한다."""
    leg = facet.fig.legends[0]
    n_before = len(leg.get_texts())
    handles_before = list(getattr(leg, "legend_handles", []))

    for name, value in [("frameon", False), ("title", "Group"),
                        ("fontsize", 9.0), ("loc", "upper right")]:
        facet.set_prop("fig.legend", name, value)

    leg = facet.fig.legends[0]
    assert len(leg.get_texts()) == n_before, "범례 항목이 사라졌습니다"
    assert list(getattr(leg, "legend_handles", [])) == handles_before
    assert leg.get_title().get_text() == "Group"
    assert leg.get_frame_on() is False
    assert leg.get_texts()[0].get_fontsize() == 9.0


def test_figure_legend_roundtrips(facet):
    for name, value in [("frameon", False), ("fontsize", 9.0),
                        ("title", "Group"), ("loc", "upper right")]:
        facet.set_prop("fig.legend", name, value)

    result = parse.parse_source(facet.preview_code())
    assert result.unhandled == []
    assert result.spec.of("fig.legend") == {
        "fontsize": 9.0, "frameon": False, "loc": "upper right",
        "title": "Group"}


def test_figure_legend_absent_is_a_no_op(tmp_path):
    """범례가 없는 figure에 override를 걸어도 만들어내지 않는다."""
    p = tmp_path / "p.py"
    p.write_text("import matplotlib.pyplot as plt\n"
                 "fig, ax = plt.subplots()\n"
                 "ax.plot([0,1],[0,1])\n", encoding="utf-8")
    s = Session()
    s.open(p)
    assert not s.fig.legends
    s.set_prop("fig.legend", "frameon", False)
    assert not s.fig.legends, "없던 figure 범례가 생겼습니다"


def test_figure_legend_survives_save_reopen(facet, tmp_path):
    facet.set_prop("fig.legend", "title", "Group")
    facet.set_prop("fig.legend", "frameon", False)
    facet.save()
    a = tmp_path / "a.png"
    facet.export(a, dpi=80)

    again = Session()
    again.open(facet.script)
    assert again.fig.legends[0].get_title().get_text() == "Group"
    b = tmp_path / "b.png"
    again.export(b, dpi=80)
    assert a.read_bytes() == b.read_bytes()


# --- 범례 전용 artist -------------------------------------------------------

HUE = """import seaborn as sns, pandas as pd, matplotlib.pyplot as plt
df = pd.DataFrame({'x': [1, 2, 3, 1, 2, 3], 'y': [1, 2, 3, 2, 3, 4],
                   'g': ['low'] * 3 + ['high'] * 3})
fig, ax = plt.subplots()
sns.lineplot(data=df, x='x', y='y', hue='g', ax=ax)
"""


@pytest.fixture
def hue(tmp_path):
    p = tmp_path / "hue.py"
    p.write_text(HUE, encoding="utf-8")
    s = Session()
    s.open(p)
    return s


def test_legend_only_artists_are_marked_in_the_tree(hue):
    """seaborn hue는 데이터 점이 0개인 Line2D를 범례용으로 남긴다.

    트리는 그것을 'line2 — high'로 보여주는데, 이름만 보면 실제 계열이다.
    색을 바꿔도 화면에 아무 일이 일어나지 않는 조용한 무동작이 되므로
    사용자가 원인을 알 수 없다. 라벨이 스스로 밝혀야 한다.
    """
    empties = [ln for ln in hue.fig.axes[0].lines if len(ln.get_xdata()) == 0]
    assert empties, "seaborn이 범례 전용 artist를 만들지 않았습니다 (전제 확인)"

    labels = {n.path: n.label for n in hue.tree.walk()}
    marked = [lb for lb in labels.values() if "(범례 전용)" in lb]
    assert len(marked) == len(empties), \
        f"범례 전용 표시가 없습니다: {sorted(labels.values())}"
    # 데이터가 있는 선은 표시가 붙으면 안 된다
    assert "high" in " ".join(marked) and "low" in " ".join(marked)


def test_real_series_are_not_marked(tmp_path):
    """데이터가 있는 선까지 범례 전용으로 찍으면 표시가 무의미해진다."""
    p = tmp_path / "p.py"
    p.write_text("import matplotlib.pyplot as plt\n"
                 "fig, ax = plt.subplots()\n"
                 "ax.plot([0,1],[0,1], label='a')\n", encoding="utf-8")
    s = Session()
    s.open(p)
    assert not any("(범례 전용)" in n.label for n in s.tree.walk())


def test_legend_only_marker_is_translated(hue):
    from figtune import i18n
    i18n.set_language("en")
    s = Session()
    s.open(hue.script)
    assert any("(legend only)" in n.label for n in s.tree.walk())
