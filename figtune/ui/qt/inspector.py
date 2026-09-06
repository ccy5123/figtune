"""인스펙터 — 레지스트리에서 위젯을 자동 생성한다.

props.REGISTRY에 Prop을 하나 추가하면 GUI에도 자동으로 나타난다.
위젯 종류를 여기서 하드코딩하지 않는 것이 핵심이다.
"""

from __future__ import annotations

from matplotlib.colors import to_rgb
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from ...core import props as P
from ...core import selector as sel


# 글자색을 배경에 맞춰 뒤집는 기준. WCAG 상대휘도에서 흰 글자와 검은 글자의
# 대비가 같아지는 지점이라, 어느 쪽으로 가도 최소 대비가 보장된다.
LUMA_FLIP = 0.179


def contrasting_text(color: str) -> str:
    """이 배경 위에서 읽히는 글자색.

    색 견본에 hex를 찍어 보여주는데, 글자색을 고정하면 어두운 색에서 검정
    위 검정이 되어 아무것도 안 보인다. 검은색 눈금이 기본값이라 흔히 걸린다.
    """
    try:
        r, g, b = to_rgb(color)
    except (ValueError, TypeError):
        return "#000000"

    def linear(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    luma = 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
    return "#000000" if luma > LUMA_FLIP else "#ffffff"


class ColorButton(QPushButton):
    changed = Signal(str)

    # 스타일시트는 자식 위젯으로 번진다. 이 버튼을 부모로 삼는 색 선택
    # 대화상자까지 검은 배경을 물려받아 글자가 하나도 안 보이게 된다.
    # 그래서 객체 이름으로 이 위젯 하나에만 걸리도록 좁힌다.
    OBJECT_NAME = "figtuneSwatch"

    def __init__(self, value: str | None = None):
        super().__init__()
        self.setObjectName(self.OBJECT_NAME)
        self.setFixedHeight(24)
        self._value = value or "#000000"
        self.setValue(self._value)
        self.clicked.connect(self._pick)

    def setValue(self, v: str | None):
        self._value = v or "#000000"
        self.setStyleSheet(
            f"QPushButton#{self.OBJECT_NAME} {{"
            f" background:{self._value};"
            f" color:{contrasting_text(self._value)};"
            " border:1px solid #888; border-radius:3px; }")
        self.setText(self._value)

    def value(self) -> str:
        return self._value

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._value), self, "색 선택")
        if c.isValid():
            self.setValue(c.name())
            self.changed.emit(c.name())


class Tuple2Widget(QWidget):
    changed = Signal(list)

    def __init__(self, lo=None, hi=None, step=0.1):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.a, self.b = QDoubleSpinBox(), QDoubleSpinBox()
        for s in (self.a, self.b):
            s.setRange(lo if lo is not None else -1e9, hi if hi is not None else 1e9)
            s.setSingleStep(step or 0.1)
            s.setDecimals(3)
            s.setKeyboardTracking(False)
            s.valueChanged.connect(lambda _=None: self.changed.emit(self.value()))
            lay.addWidget(s)

    def setValue(self, v):
        if not v:
            return
        for s, x in ((self.a, v[0]), (self.b, v[1])):
            s.blockSignals(True)
            s.setValue(float(x))
            s.blockSignals(False)

    def value(self) -> list:
        return [self.a.value(), self.b.value()]


class LocatorWidget(QWidget):
    changed = Signal(dict)

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.kind = QComboBox()
        self.kind.addItems(["auto", "multiple", "maxn", "autominor", "null"])
        self.num = QDoubleSpinBox()
        self.num.setRange(0.0001, 1e6)
        self.num.setDecimals(4)
        self.num.setValue(1.0)
        self.num.setKeyboardTracking(False)
        lay.addWidget(self.kind)
        lay.addWidget(self.num)
        self.kind.currentTextChanged.connect(self._emit)
        self.num.valueChanged.connect(lambda _: self._emit())

    def _emit(self):
        self.num.setEnabled(self.kind.currentText() in ("multiple", "maxn"))
        self.changed.emit(self.value())

    def setValue(self, v):
        v = v or {"kind": "auto"}
        self.kind.blockSignals(True)
        self.num.blockSignals(True)
        self.kind.setCurrentText(v.get("kind", "auto"))
        if v.get("kind") == "multiple":
            self.num.setValue(float(v.get("base", 1)))
        elif v.get("kind") == "maxn":
            self.num.setValue(float(v.get("n", 5)))
        self.num.setEnabled(v.get("kind") in ("multiple", "maxn"))
        self.kind.blockSignals(False)
        self.num.blockSignals(False)

    def value(self) -> dict:
        k = self.kind.currentText()
        if k == "multiple":
            return {"kind": "multiple", "base": self.num.value()}
        if k == "maxn":
            return {"kind": "maxn", "n": int(self.num.value())}
        return {"kind": k}


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
        self._empty = QLabel("캔버스나 트리에서 요소를 선택하세요.")
        self._empty.setStyleSheet("color:#888; padding:12px;")
        self._lay.addWidget(self._empty)

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
            w = self._make(prop, values.get(prop.name))
            if w is None:
                continue
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.addWidget(w, 1)
            clr = QToolButton()
            clr.setText("↺")
            clr.setToolTip("이 속성의 override 제거")
            clr.setFixedWidth(22)
            clr.clicked.connect(lambda _=False, n=prop.name: self.reset.emit(self._path, n))
            rl.addWidget(clr)

            lbl = QLabel(prop.label)
            if prop.name in overridden:
                lbl.setText(f"<b>{prop.label}</b>")
                lbl.setToolTip("figtune이 지정한 값 (override)")
            form.addRow(lbl, row)
            self._rows[prop.name] = (prop, w)
        self._blocked = False

    def _emit(self, name: str, value):
        if not self._blocked and self._path:
            self.edited.emit(self._path, name, value)

    def _make(self, prop: P.Prop, value):
        n = prop.name
        if prop.kind == "color":
            w = ColorButton(value)
            w.changed.connect(lambda v, n=n: self._emit(n, v))
            return w
        if prop.kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(value))
            w.toggled.connect(lambda v, n=n: self._emit(n, v))
            return w
        if prop.kind == "choice":
            w = QComboBox()
            w.addItems([str(c) for c in prop.choices])
            if value is not None and str(value) in prop.choices:
                w.setCurrentText(str(value))
            w.currentTextChanged.connect(lambda v, n=n: self._emit(n, v))
            return w
        if prop.kind == "float":
            w = QDoubleSpinBox()
            w.setRange(prop.lo if prop.lo is not None else -1e9,
                       prop.hi if prop.hi is not None else 1e9)
            w.setSingleStep(prop.step or 0.1)
            w.setDecimals(2)
            w.setKeyboardTracking(False)
            if value is not None:
                w.setValue(float(value))
            w.valueChanged.connect(lambda v, n=n: self._emit(n, v))
            return w
        if prop.kind == "int":
            w = QSpinBox()
            w.setRange(int(prop.lo or -10**6), int(prop.hi or 10**6))
            w.setKeyboardTracking(False)
            if value is not None:
                w.setValue(int(value))
            w.valueChanged.connect(lambda v, n=n: self._emit(n, v))
            return w
        if prop.kind == "tuple2":
            w = Tuple2Widget(prop.lo, prop.hi, prop.step)
            w.setValue(value)
            w.changed.connect(lambda v, n=n: self._emit(n, v))
            return w
        if prop.kind == "locator":
            w = LocatorWidget()
            w.setValue(value)
            w.changed.connect(lambda v, n=n: self._emit(n, v))
            return w
        if prop.kind in ("str", "strlist", "floatlist"):
            w = QLineEdit()
            if prop.kind == "str":
                w.setText("" if value is None else str(value))
                w.editingFinished.connect(lambda n=n, w=w: self._emit(n, w.text()))
            else:
                w.setText("" if not value else ", ".join(str(v) for v in value))
                w.setPlaceholderText("쉼표로 구분")
                w.editingFinished.connect(
                    lambda n=n, w=w, k=prop.kind: self._emit(
                        n, _split(w.text(), k)))
            return w
        return None

    def refresh_values(self, values: dict):
        self._blocked = True
        for name, (prop, w) in self._rows.items():
            v = values.get(name)
            if v is None:
                continue
            if isinstance(w, ColorButton):
                w.setValue(v)
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(v))
            elif isinstance(w, QComboBox):
                w.setCurrentText(str(v))
            elif isinstance(w, (QDoubleSpinBox, QSpinBox)):
                w.setValue(type(w.value())(v))
            elif isinstance(w, (Tuple2Widget, LocatorWidget)):
                w.setValue(v)
            elif isinstance(w, QLineEdit):
                w.setText(str(v) if not isinstance(v, list)
                          else ", ".join(str(x) for x in v))
        self._blocked = False

    def _clear(self):
        self._rows.clear()
        while self._lay.count() > 1:
            item = self._lay.takeAt(1)
            if item.widget():
                item.widget().deleteLater()


def _split(text: str, kind: str):
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if kind == "floatlist":
        out = []
        for p in parts:
            try:
                out.append(float(p))
            except ValueError:
                pass
        return out
    return parts
