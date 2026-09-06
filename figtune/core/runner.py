"""사용자 스크립트 실행 → 살아있는 Figure 회수.

라이브 프리뷰를 60fps로 하려면 Figure 객체가 우리 프로세스 안에 있어야 한다.
따라서 subprocess가 아니라 격리 네임스페이스에서 exec한다.

보안 주의: 이는 임의 코드 실행이다. 자기 코드를 여는 로컬 도구이므로 v0에서는
수용하되, GUI는 실행 전 반드시 사용자에게 경로를 확인시킨다.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt

from ..i18n import t as _t
from . import provenance


@dataclass
class RunResult:
    figures: list = field(default_factory=list)
    namespace: dict = field(default_factory=dict)
    stdout: str = ""
    data_sources: list = field(default_factory=list)

    @property
    def figure(self):
        return self.figures[0] if self.figures else None


def _plot_via_function(ns: dict, src: str):
    """정규형 스크립트의 plot(ax)를 호출해 figure를 만든다.

    figsize는 __main__ 블록에 적힌 값을 그대로 쓴다. 그래야 figtune에서 본
    그림과 단독 실행 결과가 같아진다.
    """
    import ast

    fn = None
    for name in ("plot", "draw", "make_plot", "plot_panel", "render"):
        cand = ns.get(name)
        if callable(cand):
            fn = cand
            break
    if fn is None:
        return None

    figsize = None
    try:
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", None) == "subplots"):
                for kw in node.keywords:
                    if kw.arg == "figsize":
                        figsize = ast.literal_eval(kw.value)
    except (SyntaxError, ValueError):
        figsize = None

    fig, ax = plt.subplots(figsize=figsize)
    fn(ax)
    return fig


@contextmanager
def _suppressed():
    """show/savefig를 무력화한다. 프리뷰 중 창이 뜨거나 파일이 생기면 안 된다."""
    from matplotlib.figure import Figure
    real_show = plt.show
    real_fig_savefig = Figure.savefig
    plt.show = lambda *a, **k: None
    Figure.savefig = lambda self, *a, **k: None
    try:
        yield
    finally:
        plt.show = real_show
        Figure.savefig = real_fig_savefig


def run_script(path: str | Path, close_existing: bool = True) -> RunResult:
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(p)

    if close_existing:
        plt.close("all")

    ns = {"__name__": "__figtune__", "__file__": str(p)}
    src = p.read_text(encoding="utf-8")
    code = compile(src, str(p), "exec")

    sys_path_added = False
    if str(p.parent) not in sys.path:
        sys.path.insert(0, str(p.parent))
        sys_path_added = True

    cwd_before = Path.cwd()
    provenance.start()
    try:
        import os
        os.chdir(p.parent)
        with _suppressed():
            exec(code, ns)
    finally:
        import os
        os.chdir(cwd_before)
        if sys_path_added:
            try:
                sys.path.remove(str(p.parent))
            except ValueError:
                pass

    sources = provenance.collect([p.parent, cwd_before], base=p.parent)

    figs = [plt.figure(n) for n in plt.get_fignums()]
    if not figs:
        # 정규형 스크립트는 figure를 __main__ 블록에서만 만든다. 그대로면
        # figtune이 자기 정규형을 열지 못한다. plot(ax)를 찾아 직접 그린다.
        fig = _plot_via_function(ns, src)
        if fig is not None:
            figs = [fig]

    # 스크립트가 fig 변수를 명시했다면 그걸 우선한다
    named = ns.get("fig")
    if named is not None and named in figs:
        figs.remove(named)
        figs.insert(0, named)

    return RunResult(figures=figs, namespace=ns, data_sources=sources)


def child_source(script: Path, pkl: Path, meta: Path,
                 rcparams: dict | None = None) -> str:
    """자식 프로세스 부트스트랩 코드.

    rcParams는 프로세스 경계를 넘지 않는다. 부모가 얹은 기본 글꼴을 여기서
    다시 얹지 않으면, 같은 설정으로 연 같은 스크립트가 실행 모드에 따라 다른
    글꼴로 나온다. artist가 만들어진 뒤에는 소급되지 않으므로 스크립트보다
    먼저 얹어야 한다.
    """
    font = f"matplotlib.rcParams.update({dict(rcparams)!r})\n" if rcparams else ""
    return (
        provenance.CHILD_SNIPPET +
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt, pickle, json, runpy\n"
        "from matplotlib.figure import Figure\n"
        + font +
        "plt.show = lambda *a, **k: None\n"
        "Figure.savefig = lambda self, *a, **k: None\n"
        f"ns = runpy.run_path({str(script)!r})\n"
        "nums = plt.get_fignums()\n"
        "if not nums:\n"
        "    raise SystemExit('no figure was created')\n"
        "fig = ns.get('fig')\n"
        "if fig is None or fig not in [plt.figure(n) for n in nums]:\n"
        "    fig = plt.figure(nums[0])\n"
        f"pickle.dump(fig, open({str(pkl)!r}, 'wb'))\n"
        "json.dump({'mpl': matplotlib.__version__, "
        "'opened': _figtune_opened}, "
        f"open({str(meta)!r}, 'w'))\n")


def run_script_subprocess(path: str | Path, python: str | None = None,
                          timeout: int = 120,
                          rcparams: dict | None = None) -> RunResult:
    """사용자 인터프리터에서 스크립트를 돌리고 Figure만 받아온다.

    figtune이 얼려진(frozen) 앱이거나 별도 환경에 설치된 경우, 인프로세스
    exec은 사용자의 pandas/seaborn/scipy를 찾지 못한다. '스크립트가 작동한다'는
    것은 사용자 환경에 대한 사실이지 우리 인터프리터에 대한 사실이 아니기
    때문이다. 그럴 때는 스크립트를 그 환경에서 실행하고 결과 Figure를
    pickle로 건네받는다.

    제약: Figure pickle은 matplotlib 버전에 결합되어 있다. 자식과 부모의
    matplotlib 버전이 다르면 실패할 수 있으므로 버전을 함께 받아 대조한다.
    """
    import json
    import pickle
    import subprocess
    import tempfile

    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(p)
    python = python or sys.executable

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        pkl, meta = td / "fig.pkl", td / "meta.json"
        (td / "_child.py").write_text(
            child_source(p, pkl, meta, rcparams), encoding="utf-8")

        proc = subprocess.run([python, str(td / "_child.py")],
                              capture_output=True, text=True,
                              cwd=str(p.parent), timeout=timeout)
        if proc.returncode != 0 or not pkl.exists():
            raise RuntimeError(_t(
                "사용자 인터프리터에서 스크립트 실행 실패:\n{err}",
                err=proc.stderr[-2000:]))

        meta_text = meta.read_text()
        child_mpl = json.loads(meta_text).get("mpl", "?")
        if child_mpl.split(".")[:2] != matplotlib.__version__.split(".")[:2]:
            raise RuntimeError(_t(
                "matplotlib 버전이 다릅니다 (스크립트 환경 {child}, "
                "figtune {ours}). Figure pickle은 버전에 결합되어 있어 "
                "안전하게 주고받을 수 없습니다. figtune을 같은 환경에 "
                "설치하거나 인프로세스 모드를 쓰세요.",
                child=child_mpl, ours=matplotlib.__version__))

        try:
            fig = pickle.loads(pkl.read_bytes())
        except Exception as exc:
            raise RuntimeError(_t("Figure를 옮겨오지 못했습니다: {err}",
                                  err=exc)) from exc

    meta_d = json.loads(meta_text)
    sources = provenance.collect_from(meta_d.get("opened", []), [p.parent],
                                      base=p.parent)
    return RunResult(figures=[fig], stdout=proc.stdout, data_sources=sources)
