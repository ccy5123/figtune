"""VBA 애드인이 호출하는 다리.

VBA에는 zlib이 없고 base64도 다루기 번거롭다. payload 인코딩을 VBA에서
재구현하면 파이썬 쪽과 어긋날 위험이 크므로, 형식을 아는 쪽에 위임한다.
애드인은 파일을 주고받기만 한다.

    python -m figtune.office.vba_bridge pack   --script S --spec F --dpi N --out A
    python -m figtune.office.vba_bridge unpack --alt A [--spec-out F] [--script-out T]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..core.spec import Spec
from ..i18n import init as _i18n_init
from ..i18n import t as _t
from . import pptx_link as PL


def main(argv=None) -> int:
    _i18n_init()
    ap = argparse.ArgumentParser(prog="figtune.office.vba_bridge")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pack", help="spec → alt text")
    p.add_argument("--script", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--out", required=True)

    u = sub.add_parser("unpack", help=_t("alt text → spec / script 경로"))
    u.add_argument("--alt", required=True,
                   help=_t("alt text가 담긴 텍스트 파일"))
    u.add_argument("--spec-out")
    u.add_argument("--script-out")

    args = ap.parse_args(argv)

    if args.cmd == "pack":
        payload = PL.Payload(script=args.script, spec=Spec.load(args.spec),
                             dpi=args.dpi)
        Path(args.out).write_text(PL.pack(payload), encoding="utf-16")
        return 0

    alt = Path(args.alt).read_text(encoding="utf-16")
    try:
        payload = PL.unpack(alt)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if payload is None:
        print(_t("figtune 도형이 아닙니다."), file=sys.stderr)
        return 1
    if args.spec_out:
        payload.spec.dump(args.spec_out)
    if args.script_out:
        Path(args.script_out).write_text(payload.script, encoding="utf-16")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
