"""프로퍼티 종류 → 위젯.

인스펙터·미니 툴바·대화상자가 모두 여기를 쓴다. 세 곳이 각자 위젯을 만들면
props.REGISTRY가 단일 참조점이라는 원칙이 세 갈래로 갈라진다. 속성을 하나
추가했을 때 어느 한 곳에만 나타나는 것이 그 증상이다.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from matplotlib.colors import to_hex, to_rgb
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QHBoxLayout, QLineEdit, QPushButton, QSpinBox,
                               QWidget)

from ...core import palette as P_palette
from ...core import props as P
from ...i18n import t as _t


def to_hex_or(value, fallback: str) -> str:
    try:
        return to_hex(value, keep_alpha=False)
    except (ValueError, TypeError):
        return fallback


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
        # 배경은 반드시 hex로 넣는다. 'tab:blue'는 matplotlib 이름이지 Qt
        # 스타일시트 색이 아니라, 그대로 넣으면 규칙 전체가 조용히 버려져
        # 견본이 빈 버튼으로 남는다.
        shown = to_hex_or(self._value, "#000000")
        self.setStyleSheet(
            f"QPushButton#{self.OBJECT_NAME} {{"
            f" background:{shown};"
            f" color:{contrasting_text(shown)};"
            " border:1px solid #888; border-radius:3px; }")
        # 이름이 있으면 이름을 보인다 — 코드에 무엇이라 적을지가 바로 보인다.
        name = P_palette.name_of(self._value)
        self.setText(f"{name}  {shown}" if name else shown)

    def value(self) -> str:
        return self._value

    def _pick(self):
        from .palette import pick_color
        picked = pick_color(self, self._value)
        if picked:
            self.setValue(picked)
            self.changed.emit(picked)


class TupleWidget(QWidget):
    """숫자 n개를 나란히. 축 범위(2개)와 축 상자(4개)에 쓴다."""

    changed = Signal(list)

    def __init__(self, n: int = 2, lo=None, hi=None, step=0.1, decimals=3):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.boxes = []
        for _ in range(n):
            s = QDoubleSpinBox()
            s.setRange(lo if lo is not None else -1e9,
                       hi if hi is not None else 1e9)
            s.setSingleStep(step or 0.1)
            s.setDecimals(decimals)
            s.setKeyboardTracking(False)
            s.valueChanged.connect(lambda _=None: self.changed.emit(self.value()))
            lay.addWidget(s)
            self.boxes.append(s)

    def setValue(self, v):
        if not v:
            return
        for s, x in zip(self.boxes, v):
            s.blockSignals(True)
            s.setValue(float(x))
            s.blockSignals(False)

    def value(self) -> list:
        return [s.value() for s in self.boxes]


# 이름을 유지한다 — 기존 코드가 이 이름으로 격자 폭을 잡는다
class Tuple2Widget(TupleWidget):
    def __init__(self, lo=None, hi=None, step=0.1):
        super().__init__(2, lo, hi, step)


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


def split_text(text: str, kind: str):
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


def make_widget(prop: P.Prop, value, on_change) -> QWidget | None:
    """prop 하나를 편집할 위젯. 모르는 종류면 None.

    on_change(name, value) 로 알린다. 호출부가 셋(인스펙터·툴바·대화상자)이라
    시그널 이름을 통일하는 대신 콜백 하나로 받는다.
    """
    n = prop.name

    def emit(v):
        on_change(n, v)

    if prop.kind == "color":
        w = ColorButton(value)
        w.changed.connect(emit)
        return w
    if prop.kind == "bool":
        w = QCheckBox()
        w.setChecked(bool(value))
        w.toggled.connect(emit)
        return w
    if prop.kind == "choice":
        w = QComboBox()
        w.addItems([str(c) for c in prop.choices])
        if value is not None and str(value) in prop.choices:
            w.setCurrentText(str(value))
        w.currentTextChanged.connect(emit)
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
        w.valueChanged.connect(emit)
        return w
    if prop.kind == "int":
        w = QSpinBox()
        w.setRange(int(prop.lo or -10**6), int(prop.hi or 10**6))
        w.setKeyboardTracking(False)
        if value is not None:
            w.setValue(int(value))
        w.valueChanged.connect(emit)
        return w
    if prop.kind in ("tuple2", "tuple4"):
        w = TupleWidget(2 if prop.kind == "tuple2" else 4,
                        prop.lo, prop.hi, prop.step)
        w.setValue(value)
        w.changed.connect(emit)
        return w
    if prop.kind == "font":
        # 목록은 matplotlib 기준이어야 한다 — 그림 속 글자를 그리는 쪽이다
        from .fontpicker import FontCombo
        w = FontCombo(value)
        w.changed.connect(emit)
        return w
    if prop.kind == "locator":
        w = LocatorWidget()
        w.setValue(value)
        w.changed.connect(emit)
        return w
    if prop.kind in ("str", "strlist", "floatlist"):
        w = QLineEdit()
        if prop.kind == "str":
            w.setText("" if value is None else str(value))
            w.editingFinished.connect(lambda: emit(w.text()))
        else:
            w.setText("" if not value else ", ".join(str(v) for v in value))
            w.setPlaceholderText(_t("쉼표로 구분"))
            w.editingFinished.connect(
                lambda: emit(split_text(w.text(), prop.kind)))
        return w
    return None


def set_widget_value(w: QWidget, value) -> None:
    """되읽기. 시그널은 호출부가 막는다."""
    if isinstance(w, ColorButton):
        w.setValue(value)
    elif isinstance(w, QCheckBox):
        w.setChecked(bool(value))
    elif isinstance(w, QComboBox):
        w.setCurrentText(str(value))
    elif isinstance(w, (QDoubleSpinBox, QSpinBox)):
        w.setValue(type(w.value())(value))
    elif hasattr(w, "setValue") and not isinstance(w, QLineEdit):
        w.setValue(value)
    elif isinstance(w, QLineEdit):
        w.setText(str(value) if not isinstance(value, list)
                  else ", ".join(str(x) for x in value))
