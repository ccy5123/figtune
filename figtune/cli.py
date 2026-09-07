"""figtune 명령줄 진입점.

서브커맨드는 PowerPoint 애드인이 호출할 안정된 계약이기도 하다.
출력 형식과 종료 코드를 함부로 바꾸지 말 것.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import i18n
from .i18n import t as _t

SUBCOMMANDS = {"edit", "render", "refresh", "merge", "normalize"}


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="figtune",
        description=_t("matplotlib figure를 GUI로 미세조정하고 코드로 남깁니다."))
    ap.add_argument("--lang", choices=(*i18n.LANGUAGES, "auto"),
                    help=_t("메시지 언어 (기본: 시스템 설정을 따름)"))
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--python", metavar="PATH",
                       help=_t("스크립트를 실행할 인터프리터 "
                               "(다른 venv/얼려진 앱인 경우)"))
        p.add_argument("--dpi", type=int, default=300)
        return p

    e = common(sub.add_parser(
        "edit", help=_t("GUI로 편집 (PowerPoint 애드인이 호출)")))
    e.add_argument("script")
    e.add_argument("--spec-in", metavar="PATH",
                   help=_t("시작 spec (없으면 디스크에서)"))
    e.add_argument("--spec-out", metavar="PATH",
                   help=_t("저장 시 spec을 여기에도 기록"))
    e.add_argument("--png-out", metavar="PATH",
                   help=_t("저장 시 이미지를 여기에도 기록"))

    r = common(sub.add_parser("render", help=_t("GUI 없이 이미지만 생성")))
    r.add_argument("script")
    r.add_argument("--spec-in", metavar="PATH")
    r.add_argument("-o", "--out", required=True)

    f = common(sub.add_parser(
        "refresh", help=_t("pptx 안의 figtune 그림을 모두 재생성")))
    f.add_argument("deck")
    f.add_argument("-o", "--out", help=_t("다른 파일로 저장 (기본: 덮어쓰기)"))
    f.add_argument("--check", action="store_true",
                   help=_t("쓰지 않고 무엇이 바뀌는지만 보고"))

    m = common(sub.add_parser(
        "merge", help=_t("여러 패널 스크립트를 하나의 figure로 합침")))
    m.add_argument("scripts", nargs="+", help=_t("패널 스크립트들 (배치 순서대로)"))
    m.add_argument("-o", "--out", required=True,
                   help=_t("생성할 병합 스크립트 (.py)"))
    m.add_argument("--rows", type=int)
    m.add_argument("--cols", type=int)
    m.add_argument("--panel-size", default="4x3", metavar="WxH",
                   help=_t("패널 하나의 크기(인치). 기본 4x3"))
    m.add_argument("--labels", default="({a})",
                   help=_t("패널 라벨 서식. 기본 '({a})'. 끄려면 빈 문자열"))
    m.add_argument("--svg", metavar="PATH",
                   help=_t("모드 B가 불가능할 때 SVG 합성으로 대신 출력"))
    m.add_argument("--edit", action="store_true", help=_t("생성 후 GUI를 연다"))
    m.add_argument("--normalize", action="store_true",
                   help=_t("정규형이 아닌 스크립트를 먼저 *_norm.py로 변환"))

    z = sub.add_parser("normalize", help=_t("스크립트를 정규형으로 변환"))
    z.add_argument("scripts", nargs="+")
    z.add_argument("--check", action="store_true",
                   help=_t("변환하지 않고 판정만"))
    z.add_argument("--in-place", action="store_true",
                   help=_t("원본을 덮어쓴다 (기본은 *_norm.py 생성)"))
    return ap


def _grid(n: int, rows: int | None, cols: int | None) -> tuple[int, int]:
    """행/열이 지정되지 않으면 논문에서 흔한 모양으로 고른다."""
    if rows and cols:
        return rows, cols
    if rows:
        return rows, -(-n // rows)
    if cols:
        return -(-n // cols), cols
    return ({1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (2, 2),
             5: (2, 3), 6: (2, 3), 8: (2, 4), 9: (3, 3)}.get(n)
            or (-(-n // 3), 3))


def _load_spec(path):
    from .core.spec import Spec
    return Spec.load(path) if path else None


def _early_lang(argv: list[str]) -> str | None:
    """도움말 문구도 번역되어야 하므로 파서를 만들기 전에 언어를 정한다."""
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


def _insert_default_subcommand(argv: list[str]) -> None:
    """하위 호환: `figtune script.py` 는 `figtune edit script.py`.

    앞에 붙은 전역 옵션(--lang en 등)을 건너뛰고 첫 위치 인자를 본다.
    """
    i = 0
    while i < len(argv) and argv[i].startswith("-"):
        i += 2 if argv[i] == "--lang" else 1
    if i < len(argv) and argv[i] not in SUBCOMMANDS:
        argv.insert(i, "refresh" if argv[i].lower().endswith(".pptx") else "edit")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    i18n.init(_early_lang(argv))
    _insert_default_subcommand(argv)

    args = _build_parser().parse_args(argv)
    if args.cmd is None:
        _build_parser().print_help()
        return 2

    if args.cmd == "refresh":
        deck = Path(args.deck)
        if not deck.exists():
            print(_t("파일 없음: {path}", path=deck), file=sys.stderr)
            return 2
        from .office import pptx_link as PL
        result = PL.refresh_deck(deck, args.out, python=args.python,
                                 check_only=args.check)
        verb = _t("변경예정") if args.check else _t("갱신")
        for label in result.updated:
            d = result.data_changes.get(label) or {}
            marks = []
            if d.get("changed"):
                marks.append(_t("데이터 수정 {n}", n=len(d["changed"])))
            if d.get("added"):
                marks.append(_t("추가 {n}", n=len(d["added"])))
            if d.get("removed"):
                marks.append(_t("사라짐 {n}", n=len(d["removed"])))
            note = f"  [{', '.join(marks)}]" if marks else ""
            print(f"{verb}  {label}{note}")
        for label, why in result.skipped:
            print(_t("건너뜀 {label}: {why}", label=label, why=why),
                  file=sys.stderr)
        print(result.summary())
        return 1 if result.skipped and not result.updated else 0

    if args.cmd == "normalize":
        return _normalize(args)

    if args.cmd == "merge":
        return _merge(args)

    script = Path(args.script)
    if not script.exists():
        print(_t("파일 없음: {path}", path=script), file=sys.stderr)
        return 2

    if args.cmd == "render":
        import matplotlib
        matplotlib.use("Agg")
        from .core.session import Session
        s = Session(python=args.python)
        rep = s.open(script, spec=_load_spec(args.spec_in))
        if rep.stale:
            print(_t("경고: 지문 불일치 {n}건", n=len(rep.stale)),
                  file=sys.stderr)
        s.export(args.out, dpi=args.dpi)
        print(args.out)
        return 0

    try:
        from .ui.qt.main import launch
    except ImportError:
        # Qt는 650MB라 기본 설치에 넣지 않는다. render·refresh·merge·normalize는
        # 그것 없이 돌아간다. 다만 여기까지 왔다는 것은 GUI를 열려는 것이고,
        # 그대로 두면 matplotlib 안쪽의 traceback만 뜬다 — figtune이라는 말도,
        # 무엇을 깔아야 하는지도 나오지 않아 패키지가 깨진 것처럼 보인다.
        print(_t("GUI를 열려면 Qt가 필요합니다. 다음으로 설치하세요:\n"
                 "    pip install \"figtune[gui]\"\n"
                 "Qt 없이도 render, refresh, merge, normalize는 씁니다."),
              file=sys.stderr)
        return 3
    return launch(script, python=args.python, spec_in=args.spec_in,
                  spec_out=args.spec_out, png_out=args.png_out, dpi=args.dpi,
                  lang=args.lang)


def _normalize(args) -> int:
    from .core import normalize as N

    rc = 0
    for name in args.scripts:
        p = Path(name)
        if not p.exists():
            print(_t("파일 없음: {path}", path=p), file=sys.stderr)
            rc = 2
            continue
        if args.check:
            rep = N.analyze(p.read_text(encoding="utf-8"))
            mark = "OK  " if rep.ok else _t("불가")
            print(f"{mark} {p}: {rep.reasons[0]}")
            for extra in rep.reasons[1:]:
                print(f"       {extra}")
            rc = rc or (0 if rep.ok else 1)
            continue
        dst, rep = N.normalize_file(p, in_place=args.in_place)
        if dst is None:
            print(f"{_t('불가')} {p}", file=sys.stderr)
            for r in rep.reasons:
                print(f"       {r}", file=sys.stderr)
            rc = 1
        else:
            note = _t(" (이미 정규형)") if rep.n_plot_stmts == 0 else ""
            print(f"OK   {p} → {dst}{note}")
    return rc


def _merge(args) -> int:
    from .core.montage_build import (MontageSpec, PanelRef,
                                     can_use_subplot_mode,
                                     generate_subplot_script)

    scripts = [Path(s) for s in args.scripts]
    missing = [str(s) for s in scripts if not s.exists()]
    if missing:
        print(_t("파일 없음: {path}", path=", ".join(missing)), file=sys.stderr)
        return 2

    if getattr(args, "normalize", False):
        from .core import normalize as N
        converted = []
        for sc in scripts:
            dst, rep = N.normalize_file(sc)
            if dst is None:
                print(_t("정규화 실패: {path}", path=sc), file=sys.stderr)
                for r in rep.reasons:
                    print(f"  {r}", file=sys.stderr)
                return 1
            if dst != sc:
                print(_t("정규화  {src} → {dst}", src=sc, dst=dst))
            converted.append(dst)
        scripts = converted

    rows, cols = _grid(len(scripts), args.rows, args.cols)
    try:
        w, h = (float(v) for v in args.panel_size.lower().split("x"))
    except ValueError:
        print(_t("--panel-size 형식은 WxH 입니다 (예: 4x3)"), file=sys.stderr)
        return 2

    mspec = MontageSpec(rows=rows, cols=cols,
                        label_template=args.labels or "",
                        auto_label=bool(args.labels),
                        panels=[PanelRef(script=str(s.resolve()))
                                for s in scripts])

    out = Path(args.out)
    try:
        generate_subplot_script(mspec, out, base_dir=Path.cwd(),
                                panel_size=(w, h))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        if not args.svg:
            print(_t("\n원본을 고칠 수 없다면 --svg PATH 로 SVG 합성을 쓰세요. "
                     "다만 그 결과는 하나의 Figure가 아니며 통째로 편집할 수 "
                     "없습니다."), file=sys.stderr)
            return 1
        from .core import montage as M
        from .core.montage_build import build as build_montage
        result = build_montage(mspec, base_dir=Path.cwd(), python=args.python)
        M.write(result, args.svg)
        print(_t("{path}  (SVG 합성 — 하나의 Figure가 아닙니다)", path=args.svg))
        return 0

    print(_t("{path}  ({rows}×{cols}, 패널 {n}개)",
             path=out, rows=rows, cols=cols, n=len(scripts)))
    print(_t("평범한 matplotlib 스크립트입니다. figtune으로 열어 편집하세요:"))
    print(f"  figtune {out}")
    if args.edit:
        from .ui.qt.main import launch
        return launch(out, python=args.python, lang=args.lang)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
