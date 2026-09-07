"""이름 있는 색 팔레트.

운영체제 색상환만으로는 그림 안의 다른 선과 같은 색을 다시 고를 수 없다.
matplotlib이 아는 이름을 그대로 내주는 것이 이 모듈의 전부다.
"""

import matplotlib.colors as mcolors
import pytest

from figtune.core import palette


def test_the_three_groups_are_there_in_order():
    assert [g.key for g in palette.groups()] == ["base", "tableau", "css"]


def test_only_css_is_folded_away():
    """148개를 처음부터 펼치면 자주 쓰는 앞의 18개가 화면 밖으로 밀려난다."""
    folded = {g.key for g in palette.groups() if g.collapsed}
    assert folded == {"css"}


def test_the_groups_are_exactly_matplotlib_s():
    """우리가 손으로 적은 목록이면 matplotlib이 색을 늘려도 따라가지 못한다."""
    assert {s.name for s in palette.BASE} == set(mcolors.BASE_COLORS)
    assert {s.name for s in palette.TABLEAU} == set(mcolors.TABLEAU_COLORS)
    assert {s.name for s in palette.CSS} == set(mcolors.CSS4_COLORS)


def test_base_and_tableau_keep_matplotlib_s_own_order():
    """Tableau는 기본 색 순환 순서다 — 섞으면 그림의 첫 선이 첫 칸이 아니다."""
    assert [s.name for s in palette.BASE] == list(mcolors.BASE_COLORS)
    assert [s.name for s in palette.TABLEAU] == list(mcolors.TABLEAU_COLORS)


def test_css_is_sorted_by_hue_not_by_name():
    names = [s.name for s in palette.CSS]
    assert names != sorted(names)
    hues = [mcolors.rgb_to_hsv(mcolors.to_rgb(s.hex))[0] for s in palette.CSS]
    assert hues == sorted(hues)


def test_css_order_is_the_same_every_time():
    """회색 계열은 색상도 채도도 0이다. 이름까지 열쇠로 넣지 않으면 뒤바뀐다."""
    assert [s.name for s in palette.CSS] == [s.name for s in palette._by_hue(
        dict(reversed(list(mcolors.CSS4_COLORS.items()))))]


@pytest.mark.parametrize("group", palette.groups(), ids=lambda g: g.key)
def test_every_swatch_carries_a_hex_value(group):
    """spec은 색을 hex로 접는다. 이름을 흘려보내면 저장 뒤 화면과 어긋난다."""
    for sw in group.swatches:
        assert sw.hex.startswith("#") and len(sw.hex) == 7, sw


def test_name_of_finds_the_short_name_first():
    """gray는 CSS에도 있지만 tab:gray가 아니다. 짧고 익숙한 쪽이 앞이다."""
    assert palette.name_of("#0000ff") == "b"
    assert palette.name_of("#1f77b4") == "tab:blue"
    assert palette.name_of("#228b22") == "forestgreen"


def test_name_of_shrugs_at_a_color_with_no_name():
    assert palette.name_of("#123456") is None
    assert palette.name_of("nonsense") is None


# --- 대화상자 ------------------------------------------------------------

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module", autouse=True)
def _offscreen():
    import os
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        return app
    try:
        return QApplication([])
    except Exception as exc:                    # pragma: no cover
        pytest.skip(f"Qt를 띄울 수 없습니다: {exc}")


def _swatches(dlg):
    from figtune.ui.qt.palette import Swatch
    return dlg.findChildren(Swatch)


def test_base_and_tableau_are_there_the_moment_it_opens(qapp):
    from figtune.ui.qt.palette import PaletteDialog

    dlg = PaletteDialog()
    shown = {s.hex for s in _swatches(dlg)}
    assert shown == {s.hex for s in palette.BASE} | {s.hex for s in palette.TABLEAU}


def test_css_is_not_built_until_it_is_asked_for(qapp):
    """148개를 열 때마다 미리 만들면 색 하나 고르는 창이 느려진다."""
    from figtune.ui.qt.palette import PaletteDialog

    dlg = PaletteDialog()
    before = len(_swatches(dlg))
    dlg._css_head.setChecked(True)
    assert len(_swatches(dlg)) == before + len(palette.CSS)


def test_clicking_a_swatch_hands_back_its_hex(qapp):
    from figtune.ui.qt.palette import PaletteDialog

    dlg = PaletteDialog()
    want = palette.TABLEAU[0].hex
    next(s for s in _swatches(dlg) if s.hex == want).click()
    assert dlg.chosen == want


def test_the_current_color_is_marked(qapp):
    """어느 것이 지금 색인지 모르면 되돌릴 수가 없다."""
    from figtune.ui.qt.palette import PaletteDialog

    want = palette.BASE[2].hex
    dlg = PaletteDialog(current=want)
    marked = [s.hex for s in _swatches(dlg) if s.current]
    assert marked == [want]


def test_a_named_color_is_understood_as_the_current_one(qapp):
    """figure에서 읽은 값은 'tab:blue'일 수 있다. hex로 접어야 짝이 맞는다."""
    from figtune.ui.qt.palette import PaletteDialog

    dlg = PaletteDialog(current="tab:blue")
    marked = [s.hex for s in _swatches(dlg) if s.current]
    assert marked == ["#1f77b4"]


def test_the_swatch_button_shows_the_color_name(qapp):
    """코드에 무엇이라 적을지가 바로 보여야 한다."""
    from figtune.ui.qt.widgets import ColorButton

    assert "tab:blue" in ColorButton("#1f77b4").text()
    assert ColorButton("#123456").text() == "#123456"


def test_the_swatch_button_never_puts_a_matplotlib_name_in_css(qapp):
    """'tab:blue'는 Qt 색이 아니다. 그대로 넣으면 규칙이 통째로 버려진다."""
    from figtune.ui.qt.widgets import ColorButton

    assert "background:#1f77b4" in ColorButton("tab:blue").styleSheet()
