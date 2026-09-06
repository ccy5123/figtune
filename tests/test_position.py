"""끌어서 옮기고 크기를 바꾸는 조작이 코드로 남는가.

직접 조작에서 새로 생기는 상태는 전부 '위치'와 '크기'다. 이것들이 왕복하지
않으면 화면에서 맞춰둔 배치가 재실행 때 사라진다 — GUI가 거짓말을 하는 셈이라
figtune에서 가장 나쁜 실패다.

셋의 API가 제각각이라는 것이 함정이다.
  제목      Text.set_position()        축 좌표
  축 라벨   Axis.set_label_coords()    축 좌표 (label.set_position()은 뜻이 다르다)
  축 상자   Axes.set_position()        figure 좌표, 값이 넷
"""

import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import pytest

from figtune.core import parse, props as P
from figtune.core.session import Session

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "plot_fig3.py"

# 캔버스에서 끌었을 때 기록되는 값들
DRAGS = [
    ("ax0", "position", [0.12, 0.18, 0.35, 0.7]),
    ("ax0.title", "position", [0.3, 1.04]),
    ("ax0.xlabel", "position", [0.5, -0.18]),
    ("ax0.ylabel", "position", [-0.14, 0.5]),
    ("ax0.legend", "bbox_to_anchor", [0.62, 0.28]),
]


@pytest.fixture
def session(tmp_path):
    dst = tmp_path / "plot_fig3.py"
    shutil.copy(EXAMPLE, dst)
    s = Session()
    s.open(dst)
    return s


# --- 왕복 -----------------------------------------------------------------

def test_every_drag_survives_the_roundtrip(session):
    for path, name, value in DRAGS:
        session.set_prop(path, name, value)
    result = parse.parse_source(session.preview_code())
    assert result.unhandled == []
    for path, name, value in DRAGS:
        assert result.spec.get(path, name) == value, f"{path}.{name} 손실"


@pytest.mark.parametrize("path,name,value", DRAGS)
def test_each_drag_alone_survives(session, path, name, value):
    """묶어서 통과해도 하나씩은 깨질 수 있다."""
    session.set_prop(path, name, value)
    result = parse.parse_source(session.preview_code())
    assert result.unhandled == []
    assert result.spec.get(path, name) == value


# --- 생성 코드가 올바른 API를 쓰는가 -----------------------------------------

def test_axis_label_uses_set_label_coords(session):
    """label.set_position()을 쓰면 축 좌표가 아니라 포인트 오프셋이 된다.

    문법은 맞고 뜻만 다르므로 왕복 테스트만으로는 잡히지 않는다.
    """
    session.set_prop("ax0.xlabel", "position", [0.5, -0.18])
    src = session.preview_code()
    assert "ax0.xaxis.set_label_coords(0.5, -0.18)" in src
    assert "xaxis.label.set_position" not in src


def _body(src: str) -> str:
    """apply_style 본문만. 헤더의 헬퍼에도 set_title이 나오므로 갈라내야 한다."""
    return src.split("def apply_style(fig):", 1)[1]


def test_title_uses_the_helper_not_set_title(session):
    """set_title(y=)은 폰트 속성을 초기화한다. 그래서 헬퍼로 내보낸다."""
    session.set_prop("ax0.title", "position", [0.3, 1.04])
    src = session.preview_code()
    assert "_title_pos(ax0, 0.3, 1.04)" in src
    assert "set_title(" not in _body(src)


def test_title_height_survives_a_redraw(session):
    """matplotlib은 그릴 때마다 제목 y를 다시 계산한다. 막지 않으면
    가로만 옮겨지고 높낮이는 조용히 되돌아간다."""
    session.set_prop("ax0.title", "position", [0.3, 1.25])
    session.fig.canvas.draw()
    x, y = session.fig.axes[0].title.get_position()
    assert (round(x, 4), round(y, 4)) == (0.3, 1.25)


def test_title_height_survives_in_generated_code(session, tmp_path):
    """살아있는 figure에서만 되고 재실행에서 풀리면 소용없다."""
    import json
    import subprocess
    import sys

    session.set_prop("ax0.title", "position", [0.3, 1.25])
    session.save(install_hook=True)
    runner = tmp_path / "_run_title.py"
    runner.write_text(
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import json, runpy\n"
        f"ns = runpy.run_path({str(session.script)!r})\n"
        "ns['fig'].canvas.draw()\n"
        "print(json.dumps([round(v, 4)\n"
        "                  for v in ns['fig'].axes[0].title.get_position()]))\n",
        encoding="utf-8")
    proc = subprocess.run([sys.executable, str(runner)], capture_output=True,
                          text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == [0.3, 1.25]


def test_axes_box_uses_set_position(session):
    session.set_prop("ax0", "position", [0.12, 0.18, 0.35, 0.7])
    assert "ax0.set_position([0.12, 0.18, 0.35, 0.7])" in session.preview_code()


# --- 실제로 움직이는가 ------------------------------------------------------

def test_dragging_the_box_moves_the_axes(session):
    session.set_prop("ax0", "position", [0.12, 0.18, 0.35, 0.7])
    got = [round(v, 4) for v in session.fig.axes[0].get_position().bounds]
    assert got == [0.12, 0.18, 0.35, 0.7]


def test_dragging_the_title_moves_it(session):
    session.set_prop("ax0.title", "position", [0.3, 1.04])
    x, y = session.fig.axes[0].title.get_position()
    assert (round(x, 4), round(y, 4)) == (0.3, 1.04)


def test_dragging_the_xlabel_moves_it(session):
    ax = session.fig.axes[0]
    session.set_prop("ax0.xlabel", "position", [0.4, -0.2])
    session.fig.canvas.draw()
    assert ax.xaxis.label.get_transform() is ax.transAxes
    x, y = ax.xaxis.label.get_position()
    assert (round(x, 4), round(y, 4)) == (0.4, -0.2)


# --- 현재값 읽기 -----------------------------------------------------------

def test_axes_box_reads_back_as_four_numbers(session):
    v = P.get(session.fig, "ax0", "position")
    assert isinstance(v, list) and len(v) == 4
    assert all(isinstance(x, float) for x in v)


def test_title_position_reads_axes_coordinates(session):
    x, y = P.get(session.fig, "ax0.title", "position")
    assert 0.0 <= x <= 1.0 and 0.9 <= y <= 1.2


def test_untouched_label_position_is_derived_not_raw(session):
    """set_label_coords 전에는 get_position()이 포인트 오프셋을 준다.

    그 값을 그대로 보여주면 끌지도 않았는데 23.6 같은 숫자가 뜬다.
    그려진 자리에서 역산해 축 좌표로 돌려줘야 한다.
    """
    session.fig.canvas.draw()
    raw = session.fig.axes[0].xaxis.label.get_position()
    assert raw[1] > 1.5, "전제가 깨졌다 — matplotlib이 이미 축 좌표를 준다"

    x, y = P.get(session.fig, "ax0.xlabel", "position")
    assert 0.0 <= x <= 1.0
    assert -1.0 < y < 0.0, f"축 아래여야 하는데 {y}"


def test_label_position_reads_back_what_was_set(session):
    session.set_prop("ax0.ylabel", "position", [-0.16, 0.45])
    session.fig.canvas.draw()
    got = P.get(session.fig, "ax0.ylabel", "position")
    assert [round(v, 4) for v in got] == [-0.16, 0.45]


# --- 정규화 ----------------------------------------------------------------

def test_tuple4_normalizes_to_floats():
    assert P.normalize("axes", "position", (0, 1, 2, 3)) == [0.0, 1.0, 2.0, 3.0]


def test_tuple4_rejects_garbage():
    assert P.normalize("axes", "position", "nope") is None


def test_tuple4_ignores_extra_values():
    """Bbox.bounds가 넷을 주지만 다른 경로가 더 줄 수도 있다."""
    assert P.normalize("axes", "position", (0, 1, 2, 3, 4)) == [0.0, 1.0, 2.0, 3.0]


# --- 미니 툴바 목록 ---------------------------------------------------------

def test_primary_names_all_exist_in_the_registry():
    """레지스트리를 복제하지 않고 이름으로 가리키므로 어긋날 수 있다."""
    bad = []
    for kind, names in P.PRIMARY.items():
        known = {p.name for p in P.REGISTRY.get(kind, ())}
        bad += [f"{kind}.{n}" for n in names if n not in known]
    assert not bad, bad


def test_primary_is_a_short_list():
    """다 넣으면 툴바가 대화상자가 되어 존재 이유가 없어진다."""
    long = {k: len(v) for k, v in P.PRIMARY.items() if len(v) > 5}
    assert not long, long


def test_primary_props_preserves_the_declared_order():
    got = [p.name for p in P.primary_props("line")]
    assert got == list(P.PRIMARY["line"])


def test_primary_props_is_empty_for_unknown_kinds():
    assert P.primary_props("nonesuch") == []


# --- 생성 코드가 실제로 도는가 -----------------------------------------------

def test_generated_code_runs_and_reproduces_the_layout(session, tmp_path):
    """문법만 맞고 동작이 다르면 도구 전체가 거짓말이 된다.

    생성된 스타일 모듈을 import하려면 스크립트 디렉토리가 sys.path에 있어야
    하므로, 사용자가 실제로 돌리는 방식대로 별도 프로세스에서 실행한다.
    """
    import json
    import subprocess
    import sys

    for path, name, value in DRAGS:
        session.set_prop(path, name, value)
    session.save(install_hook=True)

    runner = tmp_path / "_run.py"
    runner.write_text(
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import json, runpy\n"
        f"ns = runpy.run_path({str(session.script)!r})\n"
        "ax = ns['fig'].axes[0]\n"
        "print(json.dumps({\n"
        "    'box': [round(v, 4) for v in ax.get_position().bounds],\n"
        "    'title': [round(v, 4) for v in ax.title.get_position()],\n"
        "    'xlabel_is_axes_coords':\n"
        "        ax.xaxis.label.get_transform() is ax.transAxes,\n"
        "    'xlabel': [round(v, 4) for v in ax.xaxis.label.get_position()],\n"
        "}))\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(runner)], capture_output=True,
                          text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr

    got = json.loads(proc.stdout.strip().splitlines()[-1])
    assert got["box"] == [0.12, 0.18, 0.35, 0.7]
    assert got["title"] == [0.3, 1.04]
    assert got["xlabel_is_axes_coords"], "set_label_coords가 안 먹었습니다"
    assert got["xlabel"] == [0.5, -0.18]
