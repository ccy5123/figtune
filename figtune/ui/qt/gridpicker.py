"""격자 고르기 — PowerPoint의 표 넣기와 같은 조작.

칸 위를 훑으면 그만큼이 칠해지고, 누르면 정해진다. 숫자를 두 곳에 입력하는
것보다 몇 행 몇 열인지가 눈에 먼저 들어온다.

기하는 순수 함수(cell_at)로 두어 픽셀 없이 확인할 수 있게 한다.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...i18n import t as _t


class GridPicker(QWidget):
    """행·열 수를 훑어서 고른다."""

    picked = Signal(int, int)          # rows, cols
    changed = Signal(int, int)         # 훑는 동안의 미리보기

    MAX_ROWS = 6
    MAX_COLS = 6
    CELL = 22
    GAP = 3
    MARGIN = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        # 아무 데도 훑지 않고 눌러도 쓸 수 있는 값이 나와야 한다
        self._rows, self._cols = 1, 1
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    # --- 기하 -------------------------------------------------------------

    def sizeHint(self) -> QSize:
        return QSize(
            self.MARGIN * 2 + self.MAX_COLS * (self.CELL + self.GAP) - self.GAP,
            self.MARGIN * 2 + self.MAX_ROWS * (self.CELL + self.GAP) - self.GAP)

    def cell_at(self, x: float, y: float) -> tuple[int, int] | None:
        """좌표가 가리키는 '몇 행 몇 열'. 칸 밖이면 None.

        칸 사이 틈은 어느 칸에도 속하지 않는다. 틈에서 값이 튀면 훑는 동안
        칠해진 넓이가 깜빡인다.
        """
        step = self.CELL + self.GAP
        col, in_col = divmod(int(x) - self.MARGIN, step)
        row, in_row = divmod(int(y) - self.MARGIN, step)
        if in_col >= self.CELL or in_row >= self.CELL:
            return None
        if not (0 <= row < self.MAX_ROWS and 0 <= col < self.MAX_COLS):
            return None
        return row + 1, col + 1

    # --- 상태 -------------------------------------------------------------

    def current(self) -> tuple[int, int]:
        return self._rows, self._cols

    def label(self) -> str:
        return f"{self._rows} × {self._cols}"

    def set_current(self, rows: int, cols: int) -> None:
        rows = max(1, min(int(rows), self.MAX_ROWS))
        cols = max(1, min(int(cols), self.MAX_COLS))
        if (rows, cols) == (self._rows, self._cols):
            return
        self._rows, self._cols = rows, cols
        self.changed.emit(rows, cols)
        self.update()

    def commit(self) -> None:
        self.picked.emit(self._rows, self._cols)

    # --- 마우스 -----------------------------------------------------------

    def mouseMoveEvent(self, event):
        pos = event.position()
        cell = self.cell_at(pos.x(), pos.y())
        if cell is not None:
            self.set_current(*cell)

    def mouseReleaseEvent(self, event):
        pos = event.position()
        cell = self.cell_at(pos.x(), pos.y())
        if cell is not None:
            self.set_current(*cell)
        self.commit()

    # --- 그리기 -----------------------------------------------------------

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        step = self.CELL + self.GAP
        for r in range(self.MAX_ROWS):
            for c in range(self.MAX_COLS):
                x = self.MARGIN + c * step
                y = self.MARGIN + r * step
                on = r < self._rows and c < self._cols
                painter.setPen(QPen(QColor("#2c7be5" if on else "#c9c9c9")))
                painter.setBrush(QColor("#d7e8fb") if on else QColor("#ffffff"))
                painter.drawRect(x, y, self.CELL, self.CELL)
        painter.end()


class GridPickerPanel(QWidget):
    """피커와 '몇 행 몇 열'을 함께 보여준다.

    칠해진 넓이만으로는 5행인지 6행인지 세어야 한다. 숫자를 같이 두면
    훑는 동안 바로 읽힌다.
    """

    picked = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.picker = GridPicker(self)
        self.readout = QLabel(self.picker.label())
        self.readout.setAlignment(Qt.AlignCenter)
        self.readout.setStyleSheet("color:#555; padding:2px;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(QLabel(_t("합칠 격자를 고르세요")))
        lay.addWidget(self.picker)
        lay.addWidget(self.readout)

        self.picker.changed.connect(
            lambda *_: self.readout.setText(self.picker.label()))
        self.picker.picked.connect(self.picked)

    def current(self) -> tuple[int, int]:
        return self.picker.current()
