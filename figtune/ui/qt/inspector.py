"""인스펙터 — 레지스트리에서 위젯을 자동 생성한다.

props.REGISTRY에 Prop을 하나 추가하면 GUI에도 자동으로 나타난다.
위젯 종류를 여기서 하드코딩하지 않는 것이 핵심이다. 실제 위젯 생성은
widgets.make_widget이 맡는다 — 미니 툴바·대화상자와 같은 것을 써야
속성 하나가 어느 한 곳에만 나타나는 일이 없다.

여럿을 고르면 공통 속성만 보여준다. 어느 하나에만 있는 것을 보여주면
바꿔도 일부에만 먹어서, 화면과 결과가 어긋난다.
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
    """고른 대상들의 속성 편집기."""

    edited = Signal(str, object)           # prop, value
    reset = Signal(str)                    # prop
    committed = Signal()                   # 드래그/편집 확정

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self._paths: list[str] = []
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
        """언어 전환 시 호출. 속성 행은 show가 다시 만들어 준다."""
        self._empty.setText(_t("캔버스나 트리에서 요소를 선택하세요."))

    # --- 표시 -------------------------------------------------------------

    def show_path(self, path: str | None, values: dict, overridden: set[str]):
        self.show([path] if path else [], values, overridden)

    def show(self, paths, values: dict, overridden: set[str],
             mixed: set[str] | None = None):
        """paths를 함께 편집한다.

        values는 공통 값(모두 같을 때)이고, 값이 갈리는 속성은 mixed에 담겨
        온다. 그런 칸은 비워 둔다 — 아무 값이나 채우면 그것이 현재 값인 줄
        알고 넘어가서, 건드리지 않은 대상까지 그 값으로 덮인다.
        """
        self._clear()
        self._paths = list(paths)
        mixed = mixed or set()
        if not self._paths:
            self._empty.show()
            return
        self._empty.hide()

        kinds = [sel.parse(p).kind for p in self._paths]
        self._lay.addWidget(self._header(kinds))

        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setLabelAlignment(Qt.AlignRight)
        self._lay.addWidget(form_host)

        self._blocked = True
        for prop in P.common_props(kinds):
            is_mixed = prop.name in mixed
            w = make_widget(prop, None if is_mixed else values.get(prop.name),
                            self._emit)
            if w is None:
                continue
            form.addRow(self._label(prop, prop.name in overridden, is_mixed),
                        self._row(w, prop.name))
            self._rows[prop.name] = (prop, w)
        self._blocked = False

    def _header(self, kinds) -> QLabel:
        if len(self._paths) == 1:
            title, sub = self._paths[0], kinds[0]
        else:
            title = _t("{n}개 선택됨", n=len(self._paths))
            sub = ", ".join(sorted(set(kinds)))
        head = QLabel(f"<b>{title}</b><br><span style='color:#888'>{sub}</span>")
        head.setStyleSheet("padding:6px 4px;")
        head.setToolTip("\n".join(self._paths))
        return head

    def _label(self, prop, overridden: bool, mixed: bool) -> QLabel:
        text = _t(prop.label)
        lbl = QLabel(f"<b>{text}</b>" if overridden else text)
        tips = []
        if overridden:
            tips.append(_t("figtune이 지정한 값 (override)"))
        if mixed:
            lbl.setText(f"{lbl.text()} <span style='color:#888'>*</span>")
            tips.append(_t("고른 것들의 값이 서로 다릅니다"))
        if tips:
            lbl.setToolTip("\n".join(tips))
        return lbl

    def _row(self, w, name: str) -> QWidget:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(w, 1)
        clr = QToolButton()
        clr.setText("↺")
        clr.setToolTip(_t("이 속성의 override 제거"))
        clr.setFixedWidth(22)
        clr.clicked.connect(lambda _=False, n=name: self.reset.emit(n))
        rl.addWidget(clr)
        return row

    # --- 편집 -------------------------------------------------------------

    def _emit(self, name: str, value):
        if not self._blocked and self._paths:
            self.edited.emit(name, value)

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
