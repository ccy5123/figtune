"""Qt 없이 설치했을 때.

PySide6는 650MB다. render·refresh·merge·normalize는 그것 없이 돌아가므로
기본 설치에 넣지 않고 `figtune[gui]` extra로 뺐다.

대신 GUI를 열려는 사람이 무엇을 깔아야 하는지 알아야 한다. 그대로 두면
matplotlib 안쪽의 ImportError traceback만 뜨는데, 거기에는 figtune이라는 말도
설치 명령도 없어 패키지가 깨진 것처럼 보인다.
"""

import sys

import pytest


@pytest.fixture
def without_qt(monkeypatch):
    """ui.qt.main을 가져올 수 없는 상태를 만든다."""
    real = __builtins__["__import__"] if isinstance(__builtins__, dict) \
        else __builtins__.__import__

    def blocked(name, *a, **k):
        if name.startswith(("figtune.ui.qt", "PySide6")):
            raise ImportError("No module named 'PySide6'")
        return real(name, *a, **k)

    for mod in [m for m in sys.modules if m.startswith("figtune.ui.qt")]:
        monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setattr("builtins.__import__", blocked)


def test_opening_the_gui_says_what_to_install(tmp_path, without_qt, capsys):
    from figtune.cli import main

    p = tmp_path / "p.py"
    p.write_text("import matplotlib.pyplot as plt\n"
                 "fig, ax = plt.subplots()\nax.plot([0, 1])\n",
                 encoding="utf-8")

    code = main([str(p)])
    err = capsys.readouterr().err

    assert code == 3, "실패를 성공으로 보고하면 스크립트가 눈치채지 못한다"
    assert 'pip install "figtune[gui]"' in err, err
    assert "Traceback" not in err


def test_it_says_what_still_works_without_qt(tmp_path, without_qt, capsys):
    """'못 쓴다'로 끝내면 CLI만 필요한 사람이 650MB를 받는다."""
    from figtune.cli import main

    p = tmp_path / "p.py"
    p.write_text("import matplotlib.pyplot as plt\nfig = plt.figure()\n",
                 encoding="utf-8")
    main([str(p)])

    err = capsys.readouterr().err
    for sub in ("render", "refresh", "merge", "normalize"):
        assert sub in err, f"{sub}가 안내에 없습니다: {err}"


def test_the_headless_subcommands_do_not_reach_for_qt(tmp_path, without_qt):
    """Qt를 건드리면 CLI 전용 설치에서 통째로 못 쓰게 된다."""
    from figtune.cli import main

    p = tmp_path / "p.py"
    p.write_text("import matplotlib.pyplot as plt\n"
                 "fig, ax = plt.subplots()\nax.plot([0, 1])\n",
                 encoding="utf-8")
    out = tmp_path / "o.png"

    assert main(["render", str(p), "-o", str(out)]) == 0
    assert out.exists() and out.stat().st_size > 0
