"""스크립트 정규형 테스트.

핵심은 '되는 것을 되게 하는 것'보다 **안 되는 것을 조용히 하지 않는 것**이다.
추측해서 고치면 사용자의 그림이 소리 없이 달라진다.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import pytest

from figtune.core import normalize as N
from figtune.core.session import Session

MESSY = """import matplotlib.pyplot as plt, numpy as np
r = np.random.default_rng(2); fig, ax = plt.subplots(figsize=(5,3))
ax.plot(np.linspace(0,10,20), r.random(20)*1000, 's--'); ax.set_title('two')
ax.set_xlabel('Time (h)')
fig.tight_layout()
plt.show()
"""

ALREADY = """import matplotlib.pyplot as plt

def plot(ax):
    ax.plot([0, 1], [0, 1])
"""


def test_converts_recognized_script(tmp_path):
    out, rep = N.normalize(MESSY)
    assert rep.ok
    assert "def plot(ax):" in out
    assert 'if __name__ == "__main__":' in out
    assert "figsize=(5,3)" in out
    # 그리기는 함수 안으로, 데이터 준비는 모듈 수준에 남는다
    body = out.split("def plot(ax):")[1].split('if __name__')[0]
    assert "ax.plot(" in body and "ax.set_title(" in body
    assert "default_rng" not in body
    # figure 수준 호출은 단독 실행 블록이 대신한다
    assert "fig.tight_layout()" not in body


def test_normalized_script_still_runs_standalone(tmp_path):
    import subprocess
    import sys

    p = tmp_path / "m.py"
    p.write_text(MESSY, encoding="utf-8")
    dst, rep = N.normalize_file(p)
    assert rep.ok

    runner = tmp_path / "_r.py"
    runner.write_text(
        "import matplotlib\nmatplotlib.use('Agg')\nimport runpy\n"
        f"runpy.run_path({str(dst)!r}, run_name='__main__')\n"
        "print('ok')\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(runner)], capture_output=True,
                          text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr


def test_normalized_script_is_mode_b_ready(tmp_path):
    from figtune.core.montage_build import detect_plot_function

    p = tmp_path / "m.py"
    p.write_text(MESSY, encoding="utf-8")
    dst, _ = N.normalize_file(p)
    assert detect_plot_function(dst) == "plot"


def test_normalization_is_idempotent(tmp_path):
    once, rep1 = N.normalize(MESSY)
    twice, rep2 = N.normalize(once)
    assert rep2.ok
    assert twice == once, "두 번 돌리면 달라집니다"


def test_already_canonical_is_left_alone():
    out, rep = N.normalize(ALREADY)
    assert rep.ok and rep.n_plot_stmts == 0
    assert out == ALREADY


def test_original_file_is_not_overwritten_by_default(tmp_path):
    p = tmp_path / "m.py"
    p.write_text(MESSY, encoding="utf-8")
    dst, _ = N.normalize_file(p)
    assert dst != p
    assert p.read_text(encoding="utf-8") == MESSY


@pytest.mark.parametrize("src,needle", [
    ("import matplotlib.pyplot as plt\n"
     "fig, axes = plt.subplots(2, 2)\n"
     "axes[0,0].plot([0,1],[0,1])\n", "여러 축"),
    ("import matplotlib.pyplot as plt\n"
     "fig, ax = plt.subplots()\n"
     "for i in range(3):\n    ax.plot([0,i],[0,1])\n", "조건문·반복문"),
    ("import matplotlib.pyplot as plt\n"
     "fig1, ax1 = plt.subplots()\n"
     "fig2, ax2 = plt.subplots()\n", "정확히 하나"),
    ("import matplotlib.pyplot as plt\n"
     "fig, ax = plt.subplots()\n"
     "ax.plot([0,1],[0,1])\n"
     "fig.suptitle('all')\n", "옮길 수 없습니다"),
    ("import matplotlib.pyplot as plt\n"
     "fig, ax = plt.subplots()\n"
     "im = ax.imshow([[1,2],[3,4]])\n"
     "print(im.get_array().max())\n", "그리기 외 용도"),
])
def test_refuses_loudly_outside_recognized_subset(src, needle):
    out, rep = N.normalize(src)
    assert not rep.ok
    assert any(needle in r for r in rep.reasons), rep.reasons
    assert out == src, "실패했는데 원본이 바뀌었습니다"


def test_cli_check_reports_without_writing(tmp_path, monkeypatch, capsys):
    from figtune.cli import main

    p = tmp_path / "m.py"
    p.write_text(MESSY, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["normalize", "m.py", "--check"]) == 0
    assert not (tmp_path / "m_norm.py").exists()
    assert "OK" in capsys.readouterr().out


def test_merge_can_normalize_first(tmp_path, monkeypatch):
    from figtune.cli import main

    for i in range(2):
        (tmp_path / f"p{i}.py").write_text(MESSY, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    out = tmp_path / "merged.py"
    assert main(["merge", "p0.py", "p1.py", "-o", str(out), "--normalize"]) == 0

    s = Session()
    s.open(out)
    assert len(s.fig.axes) == 2


def test_module_level_plt_show_is_dropped():
    """모듈 수준에 남으면 import만 해도 창이 뜨거나 파일이 생긴다."""
    src = ("import matplotlib.pyplot as plt\n"
           "fig, ax = plt.subplots()\n"
           "ax.plot([0,1],[0,1])\n"
           "fig.tight_layout()\n"
           "plt.show()\n")
    out, rep = N.normalize(src)
    assert rep.ok
    head = out.split("def plot(ax):")[0]
    assert "plt.show()" not in head
    assert "plt.show()" in out.split('if __name__')[1]


def test_pyplot_state_calls_are_refused():
    """plt.title()은 어느 축을 가리키는지 알 수 없다. 옮기면 조용히 달라진다."""
    src = ("import matplotlib.pyplot as plt\n"
           "fig, ax = plt.subplots()\n"
           "ax.plot([0,1],[0,1])\n"
           "plt.title('hello')\n")
    out, rep = N.normalize(src)
    assert not rep.ok
    assert any("plt.title()" in r for r in rep.reasons), rep.reasons
    assert out == src


def test_figtune_can_open_its_own_canonical_form(tmp_path):
    """정규형을 정의해놓고 그걸 못 열면 말이 안 된다."""
    p = tmp_path / "m.py"
    p.write_text(MESSY, encoding="utf-8")
    dst, _ = N.normalize_file(p)

    s = Session()
    s.open(dst)
    assert len(s.fig.axes) == 1
    # __main__ 블록의 figsize를 그대로 써야 단독 실행과 같은 그림이 나온다
    assert tuple(round(v, 3) for v in s.fig.get_size_inches()) == (5.0, 3.0)
    assert [n.path for n in s.tree.walk() if n.kind == "line"] == ["ax0.line0"]

    s.set_prop("ax0.line0", "color", "red")
    s.save()
    assert "set_color('#ff0000')" in (
        dst.with_name(dst.stem + "_style.py").read_text(encoding="utf-8"))


# --- 완화된 범위 ------------------------------------------------------------

RELAXED = {
    "colorbar": (
        "import matplotlib.pyplot as plt, numpy as np\n"
        "fig, ax = plt.subplots()\n"
        "im = ax.imshow(np.zeros((4,4)))\n"
        "cb = fig.colorbar(im, ax=ax)\n"
        "cb.set_label('value')\n"
        "ax.set_title('heat')\n"),
    "twinx": (
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot([0,1],[0,1])\n"
        "ax2 = ax.twinx()\n"
        "ax2.plot([0,1],[1,0],'r')\n"
        "ax2.set_ylabel('right')\n"),
}


@pytest.mark.parametrize("name", sorted(RELAXED))
def test_assignments_and_colorbar_are_now_supported(name, tmp_path):
    """`im = ax.imshow(...)` 같은 단순 대입과 colorbar를 옮길 수 있다."""
    p = tmp_path / f"{name}.py"
    p.write_text(RELAXED[name], encoding="utf-8")
    dst, rep = N.normalize_file(p)
    assert rep.ok, rep.reasons

    body = dst.read_text(encoding="utf-8").split("def plot(ax):")[1]
    body = body.split("if __name__")[0]
    # 함수 안에는 fig가 없다. 그대로 옮기면 NameError가 난다.
    assert "fig." not in body
    if name == "colorbar":
        assert "ax.figure.colorbar(" in body

    s = Session()
    s.open(dst)
    assert len(s.fig.axes) == 2          # colorbar축 / twinx축
    s.set_prop("ax0.spine:top", "visible", False)
    s.save()


def test_target_names_propagate(tmp_path):
    """ax2 = ax.twinx() 다음 줄은 ax를 직접 쓰지 않아도 그리기 문장이다."""
    p = tmp_path / "t.py"
    p.write_text(RELAXED["twinx"], encoding="utf-8")
    dst, rep = N.normalize_file(p)
    assert rep.ok
    body = dst.read_text(encoding="utf-8").split("def plot(ax):")[1]
    body = body.split("if __name__")[0]
    assert "ax2.plot(" in body and "ax2.set_ylabel(" in body


def test_relaxed_normalization_is_still_idempotent():
    for src in RELAXED.values():
        once, r1 = N.normalize(src)
        twice, r2 = N.normalize(once)
        assert r1.ok and r2.ok
        assert twice == once
