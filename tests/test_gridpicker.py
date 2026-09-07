"""격자 고르기 위젯.

PowerPoint에서 표를 넣을 때처럼, 칸 위를 훑으면 그만큼이 칠해지고 누르면
정해진다. 숫자를 두 번 입력하는 것보다 몇 행 몇 열인지가 눈에 먼저 들어온다.

기하만 순수 함수로 빼서 좌표 계산을 픽셀 없이 확인한다. 화면에 무엇이
칠해지는지는 결국 current()가 정한다.
"""

import os

import pytest

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module", autouse=True)
def _offscreen():
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
    except Exception as exc:                     # pragma: no cover - 환경 의존
        pytest.skip(f"Qt를 띄울 수 없습니다: {exc}")


@pytest.fixture
def picker(qapp):
    from figtune.ui.qt.gridpicker import GridPicker

    w = GridPicker()
    yield w
    w.deleteLater()


def _center_of(w, row, col):
    """0부터 세는 (row, col) 칸의 한가운데 좌표."""
    return (w.MARGIN + col * (w.CELL + w.GAP) + w.CELL // 2,
            w.MARGIN + row * (w.CELL + w.GAP) + w.CELL // 2)


# --- 좌표 → 칸 --------------------------------------------------------------

@pytest.mark.parametrize("row,col", [(0, 0), (1, 2), (5, 5)])
def test_cell_at_maps_coordinates(picker, row, col):
    """훑는 칸이 곧 '몇 행 몇 열'이다 — 0부터 세지 않는다."""
    assert picker.cell_at(*_center_of(picker, row, col)) == (row + 1, col + 1)


def test_coordinates_outside_the_grid_are_none(picker):
    assert picker.cell_at(-5, -5) is None
    assert picker.cell_at(10_000, 10_000) is None


def test_the_gap_between_cells_belongs_to_no_cell(picker):
    """틈에서 값이 튀면 훑는 동안 칠해진 넓이가 깜빡인다."""
    x = picker.MARGIN + picker.CELL + picker.GAP // 2
    y = picker.MARGIN + picker.CELL // 2
    assert picker.cell_at(x, y) is None


# --- 상태 -------------------------------------------------------------------

def test_starts_at_one_by_one(picker):
    """아무 데도 훑지 않고 눌러도 쓸 수 있는 값이 나와야 한다."""
    assert picker.current() == (1, 1)


def test_set_current_is_clamped(picker):
    picker.set_current(0, 0)
    assert picker.current() == (1, 1)
    picker.set_current(99, 99)
    assert picker.current() == (picker.MAX_ROWS, picker.MAX_COLS)


def test_commit_emits_what_is_shown(picker):
    got = []
    picker.picked.connect(lambda r, c: got.append((r, c)))
    picker.set_current(3, 2)
    picker.commit()
    assert got == [(3, 2)]


def test_label_reads_as_rows_by_cols(picker):
    picker.set_current(3, 2)
    assert picker.label() == "3 × 2"


# --- 실제 마우스 -------------------------------------------------------------

def test_moving_and_releasing_picks_the_cell(picker):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    got = []
    picker.picked.connect(lambda r, c: got.append((r, c)))
    x, y = _center_of(picker, 2, 1)          # 3행 2열

    def ev(kind):
        # globalPos까지 주는 형태가 현행이다. 짧은 쪽은 폐기 예정이라
        # 경고가 뜨고, 언젠가 사라진다.
        p = QPointF(QPoint(x, y))
        return QMouseEvent(kind, p, p, Qt.LeftButton, Qt.LeftButton,
                           Qt.NoModifier)

    picker.mouseMoveEvent(ev(QMouseEvent.MouseMove))
    assert picker.current() == (3, 2)
    picker.mouseReleaseEvent(ev(QMouseEvent.MouseButtonRelease))
    assert got == [(3, 2)]


def test_the_widget_is_big_enough_for_every_cell(picker):
    want_w = picker.MARGIN * 2 + picker.MAX_COLS * (picker.CELL + picker.GAP)
    want_h = picker.MARGIN * 2 + picker.MAX_ROWS * (picker.CELL + picker.GAP)
    assert picker.sizeHint().width() >= want_w - picker.GAP
    assert picker.sizeHint().height() >= want_h - picker.GAP
