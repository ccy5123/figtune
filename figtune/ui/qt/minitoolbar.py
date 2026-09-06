"""선택하면 그 자리에 뜨는 문맥 도구막대.

Origin이 2020년에 도달한 결론을 옮긴다 — 자주 쓰는 서너 개는 손이 가 있는
자리에서 바로, 나머지는 대화상자에서. 전부 여기 담으면 툴바가 대화상자가
되어 존재 이유가 없어진다. 무엇을 담을지는 props.PRIMARY가 정한다.

캔버스 위에 겹치는 자식 위젯이다. 별도 창(Popup)으로 만들면 창 관리자가
포커스를 가져가 캔버스의 마우스 추적이 끊긴다.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton

from ...core import props as P
from ...core import selector as sel
from ...i18n import t as _t
from .widgets import make_widget

MARGIN = 8          # 캔버스 가장자리에서 띄울 간격
OFFSET = 14         # 클릭 지점에서 얼마나 떨어뜨릴지


class MiniToolbar(QFrame):
    edited = Signal(str, str, object)     # path, prop, value
    more = Signal()                       # 자세히 — 전체 편집기로

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self._path: str | None = None
        self._blocked = False
        self._rows: dict[str, object] = {}
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: rgba(252,252,252,244);"
            " border: 1px solid #9aa; border-radius: 5px; }")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(6, 3, 6, 3)
        self._lay.setSpacing(4)
        self.hide()

    # --- 표시 -------------------------------------------------------------

    def show_for(self, target, values: dict, at: QPoint) -> bool:
        """대상에 맞는 도구를 만들어 클릭 지점 옆에 띄운다.

        보여줄 것이 없으면 뜨지 않는다 — 빈 막대가 화면을 가리면 방해만 된다.
        """
        kind = sel.parse(target.path).kind
        props = P.primary_props(kind)
        if not props:
            self.hide_bar()
            return False

        # 다시 만들기 전에 내린다. 보이는 상태에서 갈아끼우면 새 위젯이
        # 숨겨진 채로 잡혀 레이아웃이 막대 크기를 0으로 계산한다.
        self.hide()
        self._clear()
        self._path = target.path
        self._blocked = True
        self._lay.addWidget(self._title(target))
        for prop in props:
            w = make_widget(prop, values.get(prop.name), self._emit)
            if w is None:
                continue
            w.setToolTip(_t(prop.label))
            w.setMaximumWidth(132)
            self._lay.addWidget(w)
            self._rows[prop.name] = w
        self._lay.addWidget(self._more_button())
        self._blocked = False

        # 위젯은 보이기 전까지 제 크기를 모른다(스타일이 적용되지 않는다).
        # 그래서 먼저 띄우고, 레이아웃을 굳힌 뒤, 정해진 크기로 자리를 잡는다.
        # 이 순서가 아니면 두 번째부터 막대가 찌부러진 채 뜬다.
        self.show()
        self._lay.activate()
        self.adjustSize()
        self.move(self._clamp(at))
        self.raise_()
        return True

    def _title(self, target) -> QLabel:
        lbl = QLabel(f"<b>{target.label or target.path}</b>")
        lbl.setStyleSheet("border: none; color: #444; padding-right: 2px;")
        return lbl

    def _more_button(self) -> QToolButton:
        b = QToolButton()
        b.setText("⋯")
        b.setToolTip(_t("모든 속성 보기"))
        b.setFixedWidth(24)
        b.setStyleSheet("border: none;")
        b.clicked.connect(self.more.emit)
        return b

    def _clamp(self, at: QPoint) -> QPoint:
        """캔버스 밖으로 나가지 않게 민다. 잘린 막대는 못 쓴다."""
        w, h = self.width(), self.height()
        x = min(max(MARGIN, at.x() - w // 2), self.canvas.width() - w - MARGIN)
        y = at.y() - h - OFFSET
        if y < MARGIN:                      # 위가 좁으면 아래로 내린다
            y = min(at.y() + OFFSET, self.canvas.height() - h - MARGIN)
        return QPoint(max(MARGIN, x), max(MARGIN, y))

    def keyPressEvent(self, event):
        """막대 안 입력칸에 포커스가 있을 때도 Esc가 먹어야 한다."""
        if event.key() == Qt.Key_Escape:
            self.canvas.win.clear_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def hide_bar(self):
        self._path = None
        self.hide()

    @property
    def path(self) -> str | None:
        return self._path

    @property
    def shown(self) -> bool:
        """자기 자신이 떠 있는가.

        isVisible()은 조상 창이 화면에 없으면 False다. 여기서 알고 싶은 것은
        '내가 내려가 있는가'이므로 자신의 상태만 본다.
        """
        return not self.isHidden()

    # --- 갱신 -------------------------------------------------------------

    def refresh(self, values: dict):
        from .widgets import set_widget_value

        self._blocked = True
        for name, w in self._rows.items():
            v = values.get(name)
            if v is not None:
                set_widget_value(w, v)
        self._blocked = False

    def _emit(self, name: str, value):
        if not self._blocked and self._path:
            self.edited.emit(self._path, name, value)

    def _clear(self):
        self._rows.clear()
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
