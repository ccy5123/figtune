"""벡터(SVG) 그림 삽입.

python-pptx는 PIL로 이미지를 판별하므로 SVG를 거부한다. 하지만 PowerPoint
365는 SVG를 지원하며, OOXML은 이를 **PNG 대체본 + SVG 원본** 쌍으로 담는다.

    <a:blip r:embed="rId2">                     ← PNG (구형 PowerPoint용)
      <a:extLst>
        <a:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}">
          <asvg:svgBlip r:embed="rId3"/>        ← SVG (365가 이걸 그림)
        </a:ext>
      </a:extLst>
    </a:blip>

이 구조 덕분에 공유가 안전하다. SVG를 모르는 뷰어는 PNG를 보고, 아는 뷰어는
벡터를 그린다. figtune이 없어도 그림은 그냥 보인다.

── 검증 범위 ──────────────────────────────────────────────────────────
패키지 구조(파트, 관계, 콘텐츠 타입, 확장 GUID)는 테스트로 확인했으나,
**실제 PowerPoint에서 벡터로 렌더되는지는 확인하지 못했다** — 리눅스
컨테이너에 PowerPoint가 없다. Windows에서 한 번 열어보고 판단할 것.
기본값은 PNG이며, 벡터는 명시적으로 켜야 한다.
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from pathlib import Path

from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from pptx.oxml.ns import qn
from pptx.util import Emu

SVG_EXT_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
SVG_NS = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
SVG_CONTENT_TYPE = "image/svg+xml"


def _next_svg_partname(package) -> PackURI:
    used = {p.partname for p in package.iter_parts()}
    n = 1
    while PackURI(f"/ppt/media/figtune{n}.svg") in used:
        n += 1
    return PackURI(f"/ppt/media/figtune{n}.svg")


def add_svg_picture(slide, svg_path, png_fallback, left, top,
                    width=None, height=None):
    """SVG 그림을 넣는다. PNG 대체본이 함께 들어간다.

    png_fallback은 같은 그림을 래스터로 뽑은 것이어야 한다. 다른 그림을 넣으면
    뷰어에 따라 다른 내용이 보이게 된다.
    """
    pic = slide.shapes.add_picture(str(png_fallback), left, top,
                                   width=width, height=height)

    part = slide.part
    svg_part = Part(_next_svg_partname(part.package), SVG_CONTENT_TYPE,
                    part.package, Path(svg_path).read_bytes())
    rId = part.relate_to(svg_part, RT.IMAGE)

    blip = pic._element.blipFill.find(qn("a:blip"))
    extLst = blip.find(qn("a:extLst"))
    if extLst is None:
        extLst = blip.makeelement(qn("a:extLst"), {})
        blip.append(extLst)

    ext = extLst.makeelement(qn("a:ext"), {"uri": SVG_EXT_URI})
    svg_blip = ext.makeelement(f"{{{SVG_NS}}}svgBlip", {qn("r:embed"): rId})
    ext.append(svg_blip)
    extLst.append(ext)
    return pic


def has_svg(shape) -> bool:
    """이 그림이 SVG 원본을 품고 있는지."""
    try:
        blip = shape._element.blipFill.find(qn("a:blip"))
    except AttributeError:
        return False
    if blip is None:
        return False
    for ext in blip.iterdescendants(qn("a:ext")):
        if ext.get("uri") == SVG_EXT_URI:
            return True
    return False


def render_pair(script, spec, out_stem: Path, dpi: int = 300,
                python: str | None = None):
    """같은 그림을 SVG와 PNG로 한 쌍 뽑는다.

    반드시 같은 Session에서 뽑아야 두 파일의 내용이 일치한다. 따로 렌더하면
    난수나 시각에 의존하는 스크립트에서 서로 다른 그림이 나올 수 있다.
    """
    import matplotlib
    matplotlib.use("Agg")
    from ..core.session import Session

    s = Session(python=python)
    s.open(script, spec=spec)
    svg = s.export(out_stem.with_suffix(".svg"), dpi=dpi)
    png = s.export(out_stem.with_suffix(".png"), dpi=dpi)
    return svg, png, s.data_changes()
