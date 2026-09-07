"""색 고르기 — matplotlib 이름 있는 색부터.

운영체제 색상환은 어떤 색이든 만들 수 있지만, 그림에 이미 쓰인 색을 다시
고를 수는 없다. matplotlib 기본 색 순환이 'tab:blue'로 그린 선 옆에 같은
파랑을 놓으려면 색상환에서 눈으로 맞춰야 한다. 그래서 이름 있는 색을 먼저
보여주고, 색상환은 그 뒤에 둔다.

CSS 148색은 접어 둔다. 처음부터 펼치면 자주 쓰는 앞의 18색이 화면 밖으로
밀려나, 흔한 선택이 가장 먼 선택이 된다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QToolButton, QVBoxLayout,
                               QWidget)

from ...core import palette as pal
from ...i18n import t as _t

SWATCH = 16                 # 견본 한 변(px)
CSS_ROWS = 14               # CSS 목록에 한 번에 보일 줄 수
COLUMNS = {"base": 4, "tableau": 2, "css": 3}


class Swatch(QToolButton):
    """색 하나. 눌리면 그 색으로 정해진다."""

    def __init__(self, sw: pal.Swatch, current: bool):
        super().__init__()
        self.hex = sw.hex
        self.current = current
        self.setFixedSize(SWATCH + 2, SWATCH + 2)
        self.setToolTip(f"{sw.name}  {sw.hex}")
        # 지금 색에는 굵은 테두리를 준다. 밝은 색에도 보이도록 어두운 선을
        # 쓰고, 흰색이 배경에 묻히지 않게 옅은 색에도 테두리를 남긴다.
        edge = "2px solid #d43" if current else "1px solid #999"
        self.setStyleSheet(
            f"QToolButton {{ background:{sw.hex}; border:{edge};"
            " border-radius:2px; }")


class PaletteDialog(QDialog):
    def __init__(self, parent=None, current: str | None = None,
                 title: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title or _t("색 선택"))
        self.chosen: str | None = None
        self._current = self._as_hex(current)

        lay = QVBoxLayout(self)
        lay.setSpacing(6)

        self._css_body: QWidget | None = None
        for group in pal.groups():
            if group.collapsed:
                self._add_collapsed(lay, group)
            else:
                lay.addWidget(QLabel(f"<b>{group.label}</b>"))
                lay.addWidget(self._grid(group))

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        lay.addWidget(line)

        row = QHBoxLayout()
        custom = QPushButton(_t("사용자 지정…"))
        custom.clicked.connect(self._custom)
        cancel = QPushButton(_t("취소"))
        cancel.clicked.connect(self.reject)
        row.addWidget(custom)
        row.addStretch(1)
        row.addWidget(cancel)
        lay.addLayout(row)

    # --- 만들기 ----------------------------------------------------------

    @staticmethod
    def _as_hex(value) -> str | None:
        from matplotlib.colors import to_hex
        try:
            return to_hex(value, keep_alpha=False)
        except (ValueError, TypeError):
            return None

    def _grid(self, group: pal.Group, names=None) -> QWidget:
        """견본 + 이름을 격자로. 이름을 함께 보여야 코드에 적을 수 있다."""
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)

        swatches = group.swatches
        if names is not None:
            swatches = [s for s in swatches if names(s.name)]
        cols = COLUMNS.get(group.key, 4)
        for i, sw in enumerate(swatches):
            btn = Swatch(sw, sw.hex == self._current)
            btn.clicked.connect(lambda _=False, h=sw.hex: self._choose(h))
            r, c = divmod(i, cols)
            grid.addWidget(btn, r, c * 2)
            grid.addWidget(QLabel(sw.name), r, c * 2 + 1)
        grid.setColumnStretch(cols * 2, 1)
        return box

    def _add_collapsed(self, lay: QVBoxLayout, group: pal.Group) -> None:
        """+ 를 눌러야 펼쳐지는 묶음.

        내용은 펼칠 때 만든다. 148개 위젯을 열 때마다 미리 만들면, 쓰지도
        않는 목록 때문에 색 하나 고르는 대화상자가 느려진다.
        """
        head = QToolButton()
        head.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        head.setArrowType(Qt.RightArrow)
        head.setCheckable(True)
        head.setAutoRaise(True)
        head.setText(_t("{label} {n}개", label=group.label,
                        n=len(group.swatches)))
        lay.addWidget(head)

        body = QWidget()
        body.setVisible(False)
        inner = QVBoxLayout(body)
        inner.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(body)
        self._css_body = body
        self._css_head = head

        def toggle(on: bool):
            head.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
            if on and inner.count() == 0:
                self._fill(inner, group)
            body.setVisible(on)
            self.adjustSize()

        head.toggled.connect(toggle)

    def _fill(self, inner: QVBoxLayout, group: pal.Group) -> None:
        find = QLineEdit()
        find.setPlaceholderText(_t("이름으로 찾기"))
        inner.addWidget(find)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFixedHeight(CSS_ROWS * (SWATCH + 4))
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(self._grid(group))
        # 세로 스크롤바가 차지할 폭까지 미리 잡아 둔다. 그러지 않으면 세로
        # 막대가 내용을 밀어 가로 막대까지 생기고, 이름 끝이 잘린다.
        bar = area.verticalScrollBar().sizeHint().width()
        area.setMinimumWidth(area.widget().sizeHint().width() + bar + 4)
        inner.addWidget(area)

        def refilter(text: str):
            needle = text.strip().lower()
            area.setWidget(self._grid(
                group, names=lambda n: needle in n.lower()))

        find.textChanged.connect(refilter)

    # --- 고르기 ----------------------------------------------------------

    def _choose(self, value: str) -> None:
        self.chosen = value
        self.accept()

    def _custom(self) -> None:
        c = QColorDialog.getColor(QColor(self._current or "#000000"), self,
                                  _t("색 선택"))
        if c.isValid():
            self._choose(c.name())


def pick_color(parent, current: str | None = None,
               title: str | None = None) -> str | None:
    """색 하나를 고르게 한다. 취소하면 None. 값은 늘 hex다.

    spec은 색을 hex 정규형으로 접는다. 이름을 그대로 돌려주면 저장 직후
    hex로 바뀌어, 방금 고른 것과 파일에 적힌 것이 달라 보인다.
    """
    dlg = PaletteDialog(parent, current, title)
    if dlg.exec() == QDialog.Accepted:
        return dlg.chosen
    return None
