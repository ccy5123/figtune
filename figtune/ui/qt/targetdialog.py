"""대상 하나를 전부 편집하는 탭 대화상자.

Origin의 Plot Details / Axis Dialog에 대응한다. 핵심은 **한 대상이 여러
selector를 묶는다**는 것 — 축을 더블클릭하면 눈금·축선·격자·범위가 한 화면에
와야 한다. 트리에서 서로 다른 가지를 네 번 오가는 것과 같은 일을 하지만,
사용자가 '이 축'이라고 생각하는 단위에 맞는다.

탭 구성은 core.hit이 만든 Target.selectors에서 파생된다. 여기서 따로 표를
들고 있으면 판정과 화면이 어긋난다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QScrollArea, QTabWidget,
                               QToolButton, QVBoxLayout, QWidget)

from ...core import props as P
from ...core import selector as sel
from ...i18n import t as _t
from .widgets import make_widget

def tab_label(path: str) -> str:
    """이 selector가 들어갈 탭 이름."""
    try:
        s = sel.parse(path)
    except sel.SelectorError:
        return path
    name = sel.KIND_LABELS.get(s.kind, s.kind)
    if s.kind == "tick" and s.which == "minor":
        return _t("보조 눈금")
    return _t(name)


class TargetDialog(QDialog):
    """대상의 모든 selector를 탭으로 펼친다."""

    edited = Signal(str, str, object)      # path, prop, value
    reset = Signal(str, str)               # path, prop

    def __init__(self, target, values_of, overridden_of, parent=None):
        """values_of(path) -> dict, overridden_of(path) -> set[str]."""
        super().__init__(parent)
        self._blocked = False
        self._rows: dict[tuple[str, str], object] = {}
        self.target = target
        self.setWindowTitle(_t("{name} 편집", name=target.label or target.path))
        self.resize(430, 520)

        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        for path in target.scope():
            page = self._page(path, values_of(path), overridden_of(path))
            if page is not None:
                self.tabs.addTab(page, tab_label(path))

        bar = QDialogButtonBox(QDialogButtonBox.Close)
        bar.rejected.connect(self.accept)
        lay.addWidget(bar)

    def _page(self, path: str, values: dict, overridden) -> QWidget | None:
        props = P.props_for(sel.parse(path).kind)
        if not props:
            return None

        host = QWidget()
        form = QFormLayout(host)
        form.setLabelAlignment(Qt.AlignRight)
        head = QLabel(f"<span style='color:#888'>{path}</span>")
        form.addRow(head)

        self._blocked = True
        made = 0
        for prop in props:
            w = make_widget(
                prop, values.get(prop.name),
                lambda name, value, p=path: self._emit(p, name, value))
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
                lambda _=False, p=path, n=prop.name: self.reset.emit(p, n))
            rl.addWidget(clr)

            lbl = QLabel(_t(prop.label))
            if prop.name in overridden:
                lbl.setText(f"<b>{_t(prop.label)}</b>")
                lbl.setToolTip(_t("figtune이 지정한 값 (override)"))
            form.addRow(lbl, row)
            self._rows[(path, prop.name)] = w
            made += 1
        self._blocked = False
        if not made:
            return None

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(host)
        return area

    def _emit(self, path, name, value):
        if not self._blocked:
            self.edited.emit(path, name, value)

    def refresh(self, values_of):
        """바깥에서 값이 바뀌었다(끌기·실행취소). 화면을 맞춘다."""
        from .widgets import set_widget_value

        self._blocked = True
        cache: dict[str, dict] = {}
        for (path, name), w in self._rows.items():
            if path not in cache:
                cache[path] = values_of(path)
            v = cache[path].get(name)
            if v is not None:
                set_widget_value(w, v)
        self._blocked = False
