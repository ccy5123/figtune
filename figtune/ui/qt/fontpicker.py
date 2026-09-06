"""글꼴 고르기.

목록은 **matplotlib 기준**이다. 그림 속 글자를 그리는 것이 matplotlib이라,
Qt 목록을 그대로 보여주면 고른 뒤 조용히 대체 글꼴로 그려진다.

미리보기는 Qt가 그린다. matplotlib 번들 글꼴은 Qt가 모르지만, 파일 경로를
QFontDatabase에 등록해 주면 알게 된다(21개에 3ms). 그래서 목록의 모든 항목을
제 글꼴로 보여줄 수 있다.

내려받기는 하지 않는다. 설치 명령과 링크만 보여주고 설치는 사용자가 한다 —
도구가 조용히 외부에 접속하면 사내망·오프라인에서 동작이 예측 불가능해진다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)

from ...core import typefaces as T
from ...i18n import t as _t

PREVIEW = "AaBbCc 123 가나다"
_registered = False


def register_with_qt() -> None:
    """matplotlib이 아는 글꼴을 Qt에도 알린다. 미리보기를 그리기 위해서다."""
    global _registered
    if _registered:
        return
    known = set(QFontDatabase.families())
    for face in T.available():
        if face.name not in known:
            QFontDatabase.addApplicationFont(face.path)
    _registered = True


def _item_font(name: str, size: int = 11) -> QFont:
    f = QFont(name)
    f.setPointSize(size)
    return f


class FontCombo(QWidget):
    """드롭다운 + 설치 안내 버튼."""

    changed = Signal(str)

    def __init__(self, value: str | None = None):
        super().__init__()
        register_with_qt()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self.combo = QComboBox()
        self.combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self._fill()
        self.setValue(value)
        self.combo.currentIndexChanged.connect(self._emit)
        lay.addWidget(self.combo, 1)

        self.more = QToolButton()
        self.more.setText("+")
        self.more.setFixedWidth(22)
        self.more.setToolTip(_t("설치할 수 있는 글꼴 더 보기"))
        self.more.clicked.connect(self._open_dialog)
        lay.addWidget(self.more)

    def _fill(self):
        """항목마다 그 글꼴로 이름을 그린다. 이름만 봐서는 고를 수 없다."""
        self.combo.blockSignals(True)
        self.combo.clear()
        for name in T.GENERIC_FAMILIES:
            self.combo.addItem(_t("{name} (총칭)", name=name), name)
            self.combo.setItemData(self.combo.count() - 1, _item_font(name),
                                   Qt.FontRole)
        self.combo.insertSeparator(self.combo.count())
        for face in T.available():
            label = f"{face.name}  —  {PREVIEW}" if face.korean else face.name
            self.combo.addItem(label, face.name)
            i = self.combo.count() - 1
            self.combo.setItemData(i, _item_font(face.name), Qt.FontRole)
            if face.korean:
                self.combo.setItemData(i, _t("한글을 그릴 수 있습니다"),
                                       Qt.ToolTipRole)
        self.combo.blockSignals(False)

    def value(self) -> str:
        return self.combo.currentData() or self.combo.currentText()

    def setValue(self, name):
        self.combo.blockSignals(True)
        idx = self.combo.findData(name)
        if idx < 0 and name:
            # spec에 있는데 이 컴퓨터에 없는 글꼴. 지우지 말고 그대로 보여준다 —
            # 값을 조용히 바꾸면 다른 사람의 그림이 달라진다.
            self.combo.addItem(f"{name}  ({_t('설치되지 않음')})", name)
            idx = self.combo.count() - 1
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)

    def _emit(self, _i):
        self.changed.emit(self.value())

    def _open_dialog(self):
        dlg = FontDialog(self.value(), self)
        dlg.exec()
        if dlg.refreshed:
            keep = self.value()
            self._fill()
            self.setValue(keep)


class FontDialog(QDialog):
    """설치할 수 있는 글꼴 안내 + 기본 글꼴 지정."""

    def __init__(self, current: str | None, parent=None):
        super().__init__(parent)
        self.refreshed = False
        self.setWindowTitle(_t("글꼴"))
        self.resize(560, 460)
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel(
            _t("figtune은 글꼴을 내려받지 않습니다. 아래 명령으로 설치한 뒤 "
               "'다시 찾기'를 누르세요.")))

        host = QWidget()
        inner = QVBoxLayout(host)
        inner.setAlignment(Qt.AlignTop)
        missing = T.missing_suggestions()
        if not missing:
            inner.addWidget(QLabel(_t("추천 글꼴이 모두 설치되어 있습니다.")))
        for sug in missing:
            inner.addWidget(self._row(sug))
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(host)
        lay.addWidget(area, 1)

        lay.addWidget(self._default_row(current))

        bar = QDialogButtonBox()
        again = bar.addButton(_t("다시 찾기"), QDialogButtonBox.ActionRole)
        again.setToolTip(_t("글꼴을 설치한 뒤 누르세요. matplotlib 목록을 "
                            "다시 만듭니다."))
        again.clicked.connect(self._refresh)
        bar.addButton(QDialogButtonBox.Close)
        bar.rejected.connect(self.reject)
        lay.addWidget(bar)

    def _row(self, sug) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(4, 6, 4, 6)
        head = QLabel(f"<b>{sug.name}</b>"
                      + (f"  <span style='color:#2a7'>{_t('한글')}</span>"
                         if sug.korean else ""))
        v.addWidget(head)
        v.addWidget(QLabel(f"<span style='color:#777'>{_t(sug.note)}</span>"))

        cmd = T.install_command(sug)
        row = QHBoxLayout()
        field = QLineEdit(cmd or sug.url)
        field.setReadOnly(True)
        field.setStyleSheet("font-family: monospace;")
        row.addWidget(field, 1)
        copy = QPushButton(_t("복사"))
        copy.clicked.connect(
            lambda _=False, s=field.text(): QGuiApplication.clipboard().setText(s))
        row.addWidget(copy)
        v.addLayout(row)
        return box

    def _default_row(self, current) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 6, 0, 0)
        saved = T.default_family()
        self.default_label = QLabel()
        self._show_default(saved)
        h.addWidget(self.default_label, 1)

        use = QPushButton(_t("현재 글꼴을 기본으로"))
        use.setEnabled(T.is_usable(current))
        use.clicked.connect(lambda: self._set_default(current))
        h.addWidget(use)

        clear = QPushButton(_t("기본 해제"))
        clear.clicked.connect(lambda: self._set_default(None))
        h.addWidget(clear)
        return box

    def _show_default(self, name):
        self.default_label.setText(
            _t("기본 글꼴: {name}", name=name) if name
            else _t("기본 글꼴: 지정 안 함 (matplotlib 기본값)"))

    def _set_default(self, name):
        T.set_default_family(name)
        self._show_default(T.default_family())

    def _refresh(self):
        """설치한 글꼴을 matplotlib이 알아보게 한다.

        matplotlib은 글꼴 목록을 캐시하고, 새로 깔아도 갱신하지 않는다.
        이 버튼이 없으면 사용자는 '깔았는데 목록에 없다'에서 막힌다.
        """
        T.rebuild()
        global _registered
        _registered = False
        register_with_qt()
        self.refreshed = True
        self.accept()
