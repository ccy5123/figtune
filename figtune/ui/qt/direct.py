"""캔버스 직접 조작 — 커서 · 끌기 · 제자리 편집.

Origin의 조작감을 옮기는 층이다. 판정(core.hit)과 계산(core.drag)은 core가
하고, 여기서는 Qt에 붙이는 일만 한다.

좌표계가 둘이라는 점만 주의하면 된다. matplotlib은 왼쪽 아래가 원점인 물리
픽셀을 쓰고, Qt 위젯은 왼쪽 위가 원점인 논리 픽셀을 쓴다. HiDPI에서는 배율만큼
어긋나므로 device_pixel_ratio로 나눠야 한다.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLineEdit

from ...core import hit

# core는 커서를 이름으로만 돌려준다. 여기서 Qt 커서로 옮긴다.
CURSORS = {
    hit.ARROW: Qt.ArrowCursor,
    hit.MOVE: Qt.SizeAllCursor,          # 열 십자 — 잡아 옮길 수 있다
    hit.TEXT: Qt.IBeamCursor,
    hit.SIZE_H: Qt.SizeHorCursor,        # ↔
    hit.SIZE_V: Qt.SizeVerCursor,        # ↕
    hit.SIZE_BDIAG: Qt.SizeBDiagCursor,  # ⤢
    hit.SIZE_FDIAG: Qt.SizeFDiagCursor,  # ⤡
}


def to_qt(canvas, x: float, y: float) -> QPoint:
    """matplotlib display 좌표 → Qt 위젯 좌표."""
    dpr = getattr(canvas, "device_pixel_ratio", 1) or 1
    return QPoint(int(round(x / dpr)), int(round(canvas.height() - y / dpr)))


def qt_rect(canvas, bbox):
    """display bbox → (좌, 상, 폭, 높이) Qt 논리 픽셀."""
    dpr = getattr(canvas, "device_pixel_ratio", 1) or 1
    left = bbox.x0 / dpr
    top = canvas.height() - bbox.y1 / dpr
    return (int(round(left)), int(round(top)),
            max(1, int(round(bbox.width / dpr))),
            max(1, int(round(bbox.height / dpr))))


class InPlaceEditor(QLineEdit):
    """글자가 있던 자리에 겹쳐 뜨는 편집기.

    한 번 클릭하면 캐럿만 놓는다. 타이핑하기 전에는 아무것도 바뀌지 않고,
    Esc면 되돌아간다 — 잘못 눌러도 그림이 상하지 않아야 한다.
    """

    committed = Signal(str, str)        # path, 새 텍스트

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self._path: str | None = None
        self._original = ""
        self.hide()
        self.setFrame(True)
        self.editingFinished.connect(self._finish)

    @property
    def active(self) -> bool:
        return self._path is not None

    def open_at(self, path: str, artist, click_x: float | None = None) -> bool:
        """artist 자리에 편집기를 띄운다. 띄우지 못하면 False."""
        try:
            bb = artist.get_window_extent(self.canvas.get_renderer())
        except Exception:
            return False

        self._path = path
        self._original = artist.get_text()
        self.setText(self._original)
        self._match_font(artist)

        left, top, w, h = qt_rect(self.canvas, bb)
        pad = 6                       # 테두리가 글자를 가리지 않게
        self.setGeometry(left - pad, top - pad, max(w + 2 * pad, 40),
                         h + 2 * pad)
        self.show()
        self.raise_()
        self.setFocus(Qt.MouseFocusReason)
        if click_x is None:
            self.setCursorPosition(len(self._original))
        else:
            dpr = getattr(self.canvas, "device_pixel_ratio", 1) or 1
            local = int(round(click_x / dpr)) - (left - pad)
            self.setCursorPosition(
                self.cursorPositionAt(QPoint(local, self.height() // 2)))
        return True

    def _match_font(self, artist):
        """화면의 글자와 크기·색을 맞춘다. 크기가 튀면 편집 중 배치가 달라 보인다."""
        f = QFont()
        try:
            dpr = getattr(self.canvas, "device_pixel_ratio", 1) or 1
            px = artist.get_fontsize() * self.canvas.figure.dpi / 72.0 / dpr
            f.setPixelSize(max(6, int(round(px))))
            f.setBold(str(artist.get_fontweight()) in ("bold", "heavy"))
            f.setItalic(str(artist.get_fontstyle()) == "italic")
        except Exception:
            pass
        self.setFont(f)
        try:
            self.setStyleSheet(
                f"color:{QColor(artist.get_color()).name()};"
                "background:rgba(255,255,255,235);"
                "border:1px solid #4a90d9;")
        except Exception:
            pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancel()
            return
        super().keyPressEvent(event)

    def cancel(self):
        self._path = None
        self.hide()
        self.canvas.setFocus()

    def commit(self):
        """확정하고 닫는다. 글자가 그대로면 아무것도 알리지 않는다."""
        path, text = self._path, self.text()
        self._path = None
        self.hide()
        if path is not None and text != self._original:
            self.committed.emit(path, text)

    def _finish(self):
        if self._path is not None:
            self.commit()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self._path is not None:
            self.commit()


def editable_artist(fig, path: str):
    """제자리 편집이 가능한 대상의 artist. 아니면 None."""
    from ...core import selector as sel

    try:
        s = sel.parse(path)
    except sel.SelectorError:
        return None
    if s.kind not in ("text", "figtext", "usertext", "txt"):
        return None
    try:
        art = sel.resolve(fig, path)
    except sel.SelectorError:
        return None
    return art if hasattr(art, "get_text") else None
