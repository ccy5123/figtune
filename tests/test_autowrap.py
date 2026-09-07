"""plot(ax) 없는 스크립트를 합칠 수 있는 형태로 감싼다.

figtune은 원본을 고치지 않는다. 감싸기는 병합 파일을 만들 때만 일어나고,
원본 스크립트는 그대로 남는다.

핵심은 '자기 figure를 만드는 줄'을 걷어내고 이미 있는 이름이 넘겨받은
axes를 가리키게 하는 것이다. 본문은 손대지 않는다 — 어느 문장이 어느
축을 건드리는지 좇기 시작하면 틀리기 시작한다.
"""

import subprocess
import sys

import matplotlib
matplotlib.use("Agg")

import pytest

from figtune.core.autowrap import (WrapError, axes_count, axes_shape,
                                   wrap_source)

PLAIN = '''"""제목 없는 스크립트."""
import matplotlib.pyplot as plt

SCALE = 2.0

fig, ax = plt.subplots(figsize=(5, 3))
ax.plot([0, 1, 2], [0, SCALE, 2 * SCALE], 'o-')
ax.set_xlabel('Time (h)')
ax.set_title('plain')
fig.tight_layout()
plt.show()
'''


# --- 몇 개의 축을 만드는가 ----------------------------------------------------

@pytest.mark.parametrize("src,want", [
    ("import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\n", 1),
    ("fig = plt.figure()\nax = fig.add_subplot(111)\n", 1),
    ("fig, axes = plt.subplots(1, 2)\n", 2),
    ("fig, axes = plt.subplots(2, 3)\n", 6),
    ("fig, axes = plt.subplots(ncols=2)\n", 2),
    ("plt.plot([0, 1], [0, 1])\n", 1),          # 상태 기반 — gca 하나
])
def test_axes_count(src, want):
    assert axes_count(src) == want


# --- 감싸기 ------------------------------------------------------------------

def test_wrapping_gives_a_function_taking_ax():
    out = wrap_source(PLAIN)
    assert out.startswith("def plot(ax):")


def test_the_figure_making_line_is_gone():
    """자기 figure를 만들면 병합 격자가 아니라 딴 데 그려진다."""
    out = wrap_source(PLAIN)
    assert "plt.subplots" not in out
    assert "plt.show" not in out


def test_module_level_code_survives():
    out = wrap_source(PLAIN)
    assert "SCALE = 2.0" in out


def test_the_body_is_untouched():
    """어느 문장이 어느 축을 건드리는지 좇기 시작하면 틀리기 시작한다."""
    out = wrap_source(PLAIN)
    assert "ax.plot([0, 1, 2], [0, SCALE, 2 * SCALE], 'o-')" in out
    assert "ax.set_title('plain')" in out


def test_fig_still_resolves():
    """본문이 fig를 쓰는 경우가 흔하다 (tight_layout, suptitle …)."""
    out = wrap_source(PLAIN)
    assert "fig = ax.figure" in out


def test_the_wrapped_panel_actually_draws(tmp_path):
    """구문만 맞고 그려지지 않으면 소용없다."""
    merged = tmp_path / "m.py"
    merged.write_text(
        "import matplotlib\nmatplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n\n"
        + wrap_source(PLAIN) + "\n\n"
        "fig, ax = plt.subplots()\n"
        "plot(ax)\n"
        "assert ax.get_title() == 'plain'\n"
        "assert ax.lines[0].get_ydata()[-1] == 4.0\n"
        "print('ok')\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(merged)], capture_output=True,
                          text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_state_based_scripts_are_wrapped(tmp_path):
    """plt.plot(...)만 쓰는 스크립트도 흔하다 — gca를 넘겨받은 축으로 돌린다."""
    src = ("import matplotlib.pyplot as plt\n"
           "plt.plot([0, 1, 2], [0, 1, 4])\n"
           "plt.xlabel('t')\n"
           "plt.title('state')\n"
           "plt.show()\n")
    merged = tmp_path / "m.py"
    merged.write_text(
        "import matplotlib\nmatplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n\n"
        + wrap_source(src) + "\n\n"
        "fig, ax = plt.subplots()\n"
        "plot(ax)\n"
        "assert ax.get_title() == 'state', ax.get_title()\n"
        "assert len(ax.lines) == 1\n"
        "print('ok')\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(merged)], capture_output=True,
                          text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr


def test_add_subplot_form_is_wrapped():
    src = ("import matplotlib.pyplot as plt\n"
           "fig = plt.figure()\n"
           "ax = fig.add_subplot(111)\n"
           "ax.plot([0, 1], [0, 1])\n")
    out = wrap_source(src)
    assert "add_subplot" not in out
    assert "plt.figure()" not in out


# --- 거부 --------------------------------------------------------------------

def test_multi_axes_scripts_are_refused():
    """2패널짜리를 한 칸에 진짜 축으로 넣을 방법이 없다."""
    src = ("import matplotlib.pyplot as plt\n"
           "fig, axes = plt.subplots(1, 2)\n"
           "axes[0].plot([0, 1], [0, 1])\n")
    with pytest.raises(WrapError, match="2개"):
        wrap_source(src)


def test_a_script_that_already_has_plot_is_left_alone():
    """이미 plot(ax)가 있으면 감쌀 이유가 없다."""
    src = ("import matplotlib.pyplot as plt\n\n"
           "def plot(ax):\n    ax.plot([0, 1], [0, 1])\n")
    with pytest.raises(WrapError, match="이미"):
        wrap_source(src)


# --- 여러 축을 만드는 스크립트 -------------------------------------------------
#
# 한 칸에 진짜 축으로 넣을 수는 없지만, 여러 칸을 주고 그 안을 스크립트
# 자신의 격자로 나누면 된다. 본문은 여전히 손대지 않는다.

MULTI = '''"""2패널 스크립트."""
import matplotlib.pyplot as plt

LW = 2.0

fig, axes = plt.subplots(1, 2, figsize=(8, 3))
axes[0].plot([0, 1], [0, 1], lw=LW)
axes[0].set_title('left')
axes[1].plot([0, 1], [1, 0], lw=LW)
axes[1].set_title('right')
plt.show()
'''


@pytest.mark.parametrize("src,want", [
    ("fig, ax = plt.subplots()\n", (1, 1)),
    ("fig, axes = plt.subplots(1, 2)\n", (1, 2)),
    ("fig, axes = plt.subplots(2, 3)\n", (2, 3)),
    ("fig, axes = plt.subplots(3)\n", (3, 1)),
    ("fig, axes = plt.subplots(nrows=2, ncols=2)\n", (2, 2)),
])
def test_axes_shape(src, want):
    assert axes_shape(src) == want


def test_multi_wrap_takes_a_list():
    out = wrap_source(MULTI, allow_multi=True)
    assert out.startswith("def plot(axs):")
    assert "axes = axs" in out


def test_multi_wrap_drops_the_figure_line():
    out = wrap_source(MULTI, allow_multi=True)
    assert "plt.subplots" not in out
    assert "plt.show" not in out


def test_multi_wrap_keeps_the_body():
    out = wrap_source(MULTI, allow_multi=True)
    assert "axes[0].set_title('left')" in out
    assert "LW = 2.0" in out


def test_the_multi_wrapped_panel_draws_into_the_given_axes(tmp_path):
    merged = tmp_path / "m.py"
    merged.write_text(
        "import matplotlib\nmatplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n\n"
        + wrap_source(MULTI, allow_multi=True) + "\n\n"
        "fig = plt.figure()\n"
        "gs = fig.add_gridspec(1, 2)\n"
        "axs = [fig.add_subplot(gs[0, i]) for i in range(2)]\n"
        "plot(axs)\n"
        "assert [a.get_title() for a in axs] == ['left', 'right']\n"
        "assert axs[0].lines[0].get_linewidth() == 2.0\n"
        "assert len(fig.axes) == 2, fig.axes\n"
        "print('ok')\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(merged)], capture_output=True,
                          text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr


def test_multi_is_still_refused_unless_asked(MULTI=MULTI):
    """기본은 거부다 — 부르는 쪽이 칸을 준비했을 때만 감싼다."""
    with pytest.raises(WrapError, match="2개"):
        wrap_source(MULTI)
