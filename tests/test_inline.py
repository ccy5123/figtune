"""패널 스크립트를 병합 파일 안으로 펼쳐 넣기.

병합 결과는 그 파일 하나로 그림이 그려져야 한다. 원본을 참조하면 파일을
옮기거나 이름을 바꾸는 순간 깨지고, 논문에 딸려 보낼 때도 폴더째 보내야 한다.

펼쳐 넣을 때 지켜야 할 것:
  · 패널마다 이름이 격리된다 (모두 plot()이라는 이름을 쓴다)
  · 모듈 수준 코드(상수, 데이터 읽기)가 살아남는다
  · __main__ 블록은 빠진다 — 남으면 자기 figure를 하나 더 만든다
  · 사람이 읽고 고칠 수 있게 원문 서식과 주석이 남는다
"""

import subprocess
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")

import pytest

from figtune.core.inline import InlineError, inline_panel

SIMPLE = '''"""패널 하나."""
import matplotlib.pyplot as plt

SCALE = 2.0          # 모듈 수준 상수


def helper(v):
    return v * SCALE


def plot(ax):
    ax.plot([0, 1, 2], [helper(0), helper(1), helper(2)])
    ax.set_title("one")


if __name__ == "__main__":
    fig, ax = plt.subplots()
    plot(ax)
'''


def test_names_are_local_to_the_panel():
    """패널마다 plot()이라는 이름을 쓴다. 격리하지 않으면 뒤엣것이 이긴다."""
    out = inline_panel(SIMPLE, "plot", "_panel_0")
    assert out.startswith("def _panel_0(ax):")
    # 모든 내용이 함수 안으로 들어갔다 — 모듈 수준에 새는 이름이 없다
    for line in out.splitlines()[1:]:
        assert not line or line.startswith("    "), f"들여쓰기 밖: {line!r}"


def test_module_level_code_survives():
    out = inline_panel(SIMPLE, "plot", "_panel_0")
    assert "SCALE = 2.0" in out
    assert "def helper(v):" in out


def test_comments_and_formatting_survive():
    """병합 파일은 사람이 이어서 고칠 코드다. 재조립하면 주석이 사라진다."""
    out = inline_panel(SIMPLE, "plot", "_panel_0")
    assert "# 모듈 수준 상수" in out


def test_main_block_is_dropped():
    """남으면 병합 스크립트를 직접 돌릴 때 자기 figure를 하나 더 만든다."""
    out = inline_panel(SIMPLE, "plot", "_panel_0")
    assert "__main__" not in out
    assert "plt.subplots()" not in out


def test_the_plot_call_is_appended():
    out = inline_panel(SIMPLE, "plot", "_panel_0")
    assert out.rstrip().endswith("plot(ax)")


def test_future_imports_are_hoisted():
    """from __future__는 모듈 맨 위에만 올 수 있다 — 함수 안에서는 SyntaxError."""
    src = ("from __future__ import annotations\n"
           "import matplotlib.pyplot as plt\n\n"
           "def plot(ax):\n    ax.plot([0, 1], [0, 1])\n")
    out = inline_panel(src, "plot", "_panel_0")
    assert "__future__" not in out


def test_file_relative_paths_are_refused():
    """__file__은 병합 파일의 것이 된다. 조용히 두면 엉뚱한 데이터를 읽는다."""
    src = ("from pathlib import Path\n"
           "DATA = Path(__file__).parent / 'd.csv'\n\n"
           "def plot(ax):\n    ax.plot([0, 1], [0, 1])\n")
    with pytest.raises(InlineError, match="__file__"):
        inline_panel(src, "plot", "_panel_0")


def test_a_missing_function_is_refused():
    src = "def draw(ax):\n    pass\n"
    with pytest.raises(InlineError, match="plot"):
        inline_panel(src, "plot", "_panel_0")


def test_two_panels_with_the_same_names_do_not_collide(tmp_path):
    """실제로 돌려서 확인한다 — 구문만 맞고 동작이 다르면 소용없다."""
    a = SIMPLE.replace('"one"', '"A"').replace("SCALE = 2.0", "SCALE = 1.0")
    b = SIMPLE.replace('"one"', '"B"').replace("SCALE = 2.0", "SCALE = 9.0")

    merged = tmp_path / "m.py"
    merged.write_text(
        "import matplotlib\nmatplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n\n"
        + inline_panel(a, "plot", "_panel_0") + "\n\n"
        + inline_panel(b, "plot", "_panel_1") + "\n\n"
        "fig, axes = plt.subplots(1, 2)\n"
        "_panel_0(axes[0])\n_panel_1(axes[1])\n"
        "assert axes[0].get_title() == 'A'\n"
        "assert axes[1].get_title() == 'B'\n"
        # SCALE이 섞이지 않았는지 — 두 번째 패널의 마지막 y는 9*2
        "assert axes[1].lines[0].get_ydata()[-1] == 18.0\n"
        "print('ok')\n", encoding="utf-8")

    proc = subprocess.run([sys.executable, str(merged)],
                          capture_output=True, text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_indentation_of_nested_blocks_is_preserved():
    src = textwrap.dedent('''
        def plot(ax):
            for i in range(3):
                if i:
                    ax.plot([i], [i])
    ''').strip() + "\n"
    out = inline_panel(src, "plot", "_panel_0")
    assert "            if i:" in out          # 4(감싸기) + 8(원문)
