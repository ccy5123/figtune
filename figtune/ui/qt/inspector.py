"""인스펙터 — 레지스트리에서 위젯을 자동 생성한다.

props.REGISTRY에 Prop을 하나 추가하면 GUI에도 자동으로 나타난다.
위젯 종류를 여기서 하드코딩하지 않는 것이 핵심이다. 실제 위젯 생성은
widgets.make_widget이 맡는다 — 미니 툴바·대화상자와 같은 것을 써야
속성 하나가 어느 한 곳에만 나타나는 일이 없다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFormLayout, QHBoxLayout, QLabel, QScrollArea,
                               QToolButton, QVBoxLayout, QWidget)

from ...core import props as P
from ...core import selector as sel
from ...i18n import t as _t
from .widgets import make_widget, set_widget_value


class Inspector(QScrollArea):
    """선택된 selector의 속성 편집기."""

    edited = Signal(str, str, object)      # path, prop, value
    reset = Signal(str, str)               # path, prop
    committed = Signal()                   # 드래그/편집 확정

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self._path: str | None = None
        self._rows: dict[str, tuple] = {}
        self._blocked = False
        self._host = QWidget()
        self.setWidget(self._host)
        self._lay = QVBoxLayout(self._host)
        self._lay.setAlignment(Qt.AlignTop)
        self._empty = QLabel(_t("캔버스나 트리에서 요소를 선택하세요."))
        self._empty.setStyleSheet("color:#888; padding:12px;")
        self._lay.addWidget(self._empty)

    def retranslate(self):
        """언어 전환 시 호출. 속성 행은 show_path가 다시 만들어 준다."""
        self._empty.setText(_t("캔버스나 트리에서 요소를 선택하세요."))

    def show_path(self, path: str | None, values: dict, overridden: set[str]):
        self._clear()
        self._path = path
        if path is None:
            self._empty.show()
            return
        self._empty.hide()

        kind = sel.parse(path).kind
        head = QLabel(f"<b>{path}</b><br><span style='color:#888'>{kind}</span>")
        head.setStyleSheet("padding:6px 4px;")
        self._lay.addWidget(head)

        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setLabelAlignment(Qt.AlignRight)
        self._lay.addWidget(form_host)

        self._blocked = True
        for prop in P.props_for(kind):
            w = make_widget(prop, values.get(prop.name), self._emit)
            if w is None:
                continue
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.addWidget(w, 1)
            clr = QToolButton()
            clr.setText("↺")
            clr.setToolTip(_t("이 속성의 override 제거"))
            clr.setFixedWidth(22)
            clr.clicked.connect(
                lambda _=False, n=prop.name: self.reset.emit(self._path, n))
            rl.addWidget(clr)

            lbl = QLabel(_t(prop.label))
            if prop.name in overridden:
                lbl.setText(f"<b>{_t(prop.label)}</b>")
                lbl.setToolTip(_t("figtune이 지정한 값 (override)"))
            form.addRow(lbl, row)
            self._rows[prop.name] = (prop, w)
        self._blocked = False

    def _emit(self, name: str, value):
        if not self._blocked and self._path:
            self.edited.emit(self._path, name, value)

    def refresh_values(self, values: dict):
        self._blocked = True
        for name, (_prop, w) in self._rows.items():
            v = values.get(name)
            if v is None:
                continue
            set_widget_value(w, v)
        self._blocked = False

    def _clear(self):
        self._rows.clear()
        while self._lay.count() > 1:
            item = self._lay.takeAt(1)
            w = item.widget()
            if w is not None:
                # 레이아웃에서 빼도 삭제 전까지는 그려진다. deleteLater는
                # 이벤트 루프가 처리하므로 그 사이 새 행과 겹쳐 보인다.
                w.hide()
                w.setParent(None)
                w.deleteLater()
