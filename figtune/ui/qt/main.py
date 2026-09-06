"""figtune 메인 윈도우."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import matplotlib
matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.backends.backend_qtagg import (                   # noqa: E402
    NavigationToolbar2QT as NavToolbar)
from PySide6.QtCore import Qt, Signal  # noqa: E402
from PySide6.QtGui import (QAction, QColor, QKeySequence,  # noqa: E402
                           QPainter, QPen)
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog,  # noqa: E402
                               QHBoxLayout, QInputDialog, QLabel, QMainWindow,
                               QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea,
                               QSplitter, QStatusBar, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ... import config  # noqa: E402
from ... import i18n  # noqa: E402
from ...core import apply as ap  # noqa: E402
from ...core import drag  # noqa: E402
from ...core import hit  # noqa: E402
from ...core import layout  # noqa: E402
from ...core import selector as sel  # noqa: E402
from ...core.history import Command  # noqa: E402
from ...core.session import Session  # noqa: E402
from ...i18n import t as _t  # noqa: E402
from . import direct  # noqa: E402
from . import fonts  # noqa: E402
from .inspector import Inspector  # noqa: E402
from .minitoolbar import MiniToolbar  # noqa: E402
from .targetdialog import TargetDialog  # noqa: E402


BASE_DPI = 100.0

# 이보다 적게 움직이면 끌기가 아니라 클릭으로 본다. 손떨림으로 글자가
# 밀리지 않을 만큼은 되고, 옮기려는 의도를 막을 만큼 크지는 않은 값.
DRAG_THRESHOLD = 3.0


def _at(event, x, y):
    """누른 지점을 기준으로 삼는 가짜 이벤트. 끌기는 누른 자리에서 시작한다."""
    from types import SimpleNamespace
    return SimpleNamespace(x=x, y=y, xdata=event.xdata, ydata=event.ydata,
                           inaxes=event.inaxes, button=event.button)


class CanvasFrame(QScrollArea):
    """캔버스를 담고 표시 배율을 관리한다.

    figure 크기(인치)는 사용자가 정하는 값이므로 위젯 크기에 맞춰 덮어쓰면
    안 된다. 대신 화면 표시용 dpi를 조절해 뷰포트에 맞춘다. 출력 dpi는
    별개이며 export 시점에만 쓰인다.
    """

    def __init__(self, canvas: "Canvas"):
        super().__init__()
        self.canvas = canvas
        self.setWidget(canvas)
        self.setAlignment(Qt.AlignCenter)
        self.setWidgetResizable(False)
        self.setStyleSheet("QScrollArea { border: none; background: #efefef; }")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def fit(self):
        fig = self.canvas.figure
        w_in, h_in = fig.get_size_inches()
        if w_in <= 0 or h_in <= 0:
            return
        vp = self.viewport().size()
        margin = 24
        scale = min((vp.width() - margin) / (w_in * BASE_DPI),
                    (vp.height() - margin) / (h_in * BASE_DPI))
        scale = max(0.15, min(scale, 3.0))
        dpi = BASE_DPI * scale
        if abs(fig.get_dpi() - dpi) > 0.5:
            fig.set_dpi(dpi)
        self.canvas.setFixedSize(int(w_in * dpi), int(h_in * dpi))
        self.canvas.draw_idle()


class Canvas(FigureCanvasQTAgg):
    """직접 조작 — 클릭으로 고르고, 끌어서 옮기고, 그 자리에서 글자를 고친다.

    판정은 core.hit이, 끌기 계산은 core.drag이 한다. 여기서 하는 일은 좌표를
    넘기고 결과를 session에 넣는 것뿐이다.
    """

    def __init__(self, window: "MainWindow"):
        super().__init__(window.session.fig)
        self.win = window
        self._map = None            # hit.HitMap — 다시 그릴 때까지 유효
        self._drag = None           # (core.drag.Drag, 시작 override 값)
        self._pending = None        # 끌기인지 제자리 편집인지 아직 모른다
        self.editor = direct.InPlaceEditor(self)
        self.editor.committed.connect(self._commit_text)
        self.bar = MiniToolbar(self)
        self.bar.edited.connect(self._bar_edit)
        self.bar.more.connect(lambda: self.open_dialog(self._target))
        self._target = None         # 마지막으로 고른 대상 (대화상자·툴바용)
        self._highlight = None      # (x, y, w, h) Qt 좌표 — 화면에만 그린다
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.mpl_connect("draw_event", lambda _e: self._after_draw())
        self.mpl_connect("button_press_event", self._press)
        self.mpl_connect("motion_notify_event", self._motion)
        self.mpl_connect("button_release_event", self._release)

    # --- 판정 지도 --------------------------------------------------------

    def _after_draw(self):
        self.invalidate_map()
        self._recompute_highlight()

    def invalidate_map(self):
        """기하가 바뀌었다. 다음에 필요할 때 다시 잰다.

        지도를 만드는 데 2패널 그림 기준 12ms가 든다. 그리기마다 곧바로 만들면
        마우스를 쓰지 않는 재생성에도 그 값을 치르므로 미뤄 둔다.
        """
        self._map = None

    def hitmap(self):
        if self._map is None:
            self._map = hit.build(self.figure)
        return self._map

    def targets_at(self, event, with_artists: bool = True):
        artists = (hit.artist_hits(self.figure, self.win.session.tree,
                                   event.x, event.y)
                   if with_artists else None)
        return self.hitmap().at(event.x, event.y,
                                selected=getattr(self.win, "_current", None),
                                artists=artists)

    # --- 클릭 -------------------------------------------------------------

    def _press(self, event):
        if event.button != 1:
            return
        if self.editor.active:
            self.editor.commit()        # 다른 곳을 누르면 확정된다

        targets = self.targets_at(event)
        target = self._disambiguate(targets)
        if target is None:
            return

        self._target = target
        self.win.select(target.path)
        if event.dblclick:
            self.open_dialog(target)
            return
        self._show_bar(target, event)
        # 제목·라벨·범례는 '한 번 클릭 = 캐럿'과 '끌어서 이동'을 같은 제스처로
        # 요구한다. 누른 시점에는 어느 쪽인지 알 수 없으므로 미뤄 두고,
        # 움직이면 이동, 안 움직이고 떼면 편집으로 가른다.
        if target.editable and target.movable:
            self._pending = (target, event.x, event.y)
            return
        if target.editable and self._open_editor(target, event):
            return
        self._start_drag(target, event)

    def _disambiguate(self, targets):
        """겹친 데이터 artist가 여럿이면 고르게 한다.

        레이어와 페이지는 늘 후보에 들어 있으므로, 그것까지 물으면 클릭마다
        메뉴가 뜬다. 진짜로 애매한 것 — 겹친 plot — 만 묻는다.
        """
        plots = [t for t in targets if t.kind == "plot"]
        if len(plots) > 1:
            menu = QMenu(self)
            acts = {menu.addAction(t.label or t.path): t for t in plots}
            chosen = menu.exec(self.cursor().pos())
            return acts.get(chosen)
        return targets[0] if targets else None

    def _open_editor(self, target, event) -> bool:
        art = direct.editable_artist(self.figure, target.path)
        if art is None:
            return False
        return self.editor.open_at(target.path, art, click_x=event.x)

    def _commit_text(self, path, text):
        s = sel.parse(path)
        if s.kind == "usertext":
            t = self.win.session.spec.text_by_id(s.name)
            if t is not None:
                t.text = text
                ap.sync_text(self.figure, self.win.session.spec, s.name)
                self.win.session.dirty = True
        else:
            self.win.session.set_prop(path, "text", text)
        self.draw_idle()
        self.win.after_edit(path)

    # --- 미니 툴바 · 대화상자 ---------------------------------------------

    def _show_bar(self, target, event):
        pos = direct.to_qt(self, event.x, event.y)
        self.bar.show_for(target, self.win.session.values(target.path), pos)

    def _bar_edit(self, path, name, value):
        self.win.session.set_prop(path, name, value)
        self.draw_idle()
        self.win.after_edit(path)

    def open_dialog(self, target):
        """대상의 모든 selector를 탭으로 펼친다."""
        if target is None:
            return
        self.bar.hide_bar()
        dlg = TargetDialog(target, self.win.session.values,
                           lambda p: set(self.win.session.spec.of(p)), self)
        dlg.edited.connect(self._bar_edit)
        dlg.reset.connect(self._dialog_reset)
        self._dialog = dlg
        dlg.finished.connect(lambda _=0: setattr(self, "_dialog", None))
        dlg.show()

    def _dialog_reset(self, path, name):
        self.win.session.reset_prop(path, name)
        self.draw_idle()
        self.win.after_edit(path)

    # --- 선택 표시 --------------------------------------------------------

    def set_highlight(self, path: str | None, target=None):
        """고른 대상에 테두리를 친다.

        Qt로 그린다. matplotlib artist로 그리면 내보낸 그림에까지 테두리가
        따라 들어간다.
        """
        self._highlight_path = path
        # 캔버스에서 고른 것이면 대상을 함께 기억한다. 트리에서 고른 경우는
        # 대상이 없으므로 path로만 맞춘다(축은 조금 넓게 잡힌다).
        self._highlight_target = target
        self._recompute_highlight()
        self.update()

    def _recompute_highlight(self):
        path = getattr(self, "_highlight_path", None)
        self._highlight = None
        if not path:
            return
        box = self.hitmap().bbox_of(
            path, getattr(self, "_highlight_target", None))
        if box is None:
            box = self._artist_box(path)
        if box is None:
            return
        dpr = getattr(self, "device_pixel_ratio", 1) or 1
        x0, y0, x1, y1 = box
        self._highlight = (x0 / dpr, self.height() - y1 / dpr,
                           (x1 - x0) / dpr, (y1 - y0) / dpr)

    def _artist_box(self, path):
        """지도에 없는 대상(선·점 등)은 artist에서 직접 잰다."""
        try:
            art = sel.resolve(self.figure, path)
            bb = art.get_window_extent(self.get_renderer())
        except Exception:
            return None
        if bb is None or bb.width <= 0 or bb.height <= 0:
            return None
        return (bb.x0, bb.y0, bb.x1, bb.y1)

    def keyPressEvent(self, event):
        """Esc면 선택을 푼다. 그림만 보고 싶을 때 겹친 것들이 거슬린다.

        제자리 편집 중이면 편집기가 포커스를 쥐고 먼저 Esc를 받아 편집을
        취소한다 — 여기까지 오지 않는다.
        """
        if event.key() == Qt.Key_Escape and self.win.has_selection():
            self.win.clear_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._highlight:
            return
        x, y, w, h = self._highlight
        painter = QPainter(self)
        pen = QPen(QColor("#2c7be5"))
        pen.setWidth(1)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(int(x) - 2, int(y) - 2, int(w) + 4, int(h) + 4)
        if sel.parse(self._highlight_path).kind == "axes":
            self._paint_handles(painter, x, y, w, h)
        painter.end()

    def _paint_handles(self, painter, x, y, w, h):
        """크기를 바꿀 수 있다는 표시. 고른 뒤에만 나타난다 — Origin과 같다."""
        painter.setPen(QPen(QColor("#2c7be5")))
        painter.setBrush(QColor("#ffffff"))
        r = 3
        for cx in (x, x + w / 2, x + w):
            for cy in (y, y + h / 2, y + h):
                if cx == x + w / 2 and cy == y + h / 2:
                    continue
                painter.drawRect(int(cx) - r, int(cy) - r, 2 * r, 2 * r)

    # --- 끌기 -------------------------------------------------------------

    def _start_drag(self, target, event):
        d, pins = drag.begin(self.figure, target, event.x, event.y)
        if d is None:
            return
        # 끌기에 딸린 확정값(범례 loc 등)은 히스토리에 따로 쌓지 않는다.
        # 따로 쌓으면 끌기 한 번을 되돌리는 데 실행 취소가 두 번 든다.
        extras = []
        for pin in pins:
            was = self.win.session.spec.of(pin.path).get(pin.prop)
            self.win.session.set_prop(pin.path, pin.prop, pin.value, record=False)
            extras.append(Command(pin.path, pin.prop, was, pin.value))
        # 직전 편집과 한 칸으로 합쳐지면 실행 취소가 둘을 한꺼번에 되돌린다
        self.win.session.history.seal()
        prop = "bbox_to_anchor" if d.kind == "legend" else "position"
        before = self.win.session.recorded_value(d.path, prop)
        self._drag = (d, before, extras)

    def _motion(self, event):
        if self._pending is not None:
            target, x0, y0 = self._pending
            if abs(event.x - x0) + abs(event.y - y0) < DRAG_THRESHOLD:
                return                       # 아직 클릭인지 끌기인지 모른다
            self._pending = None
            self._start_drag(target, _at(event, x0, y0))
        if self._drag is not None:
            self._drag_to(event)
            return
        if not self.editor.active:
            self.setCursor(direct.CURSORS.get(
                self.hitmap().cursor(
                    event.x, event.y,
                    selected=getattr(self.win, "_current", None)),
                Qt.ArrowCursor))

    def _drag_to(self, event):
        d = self._drag[0]
        # 실제로 움직이기 시작했을 때만 막대를 치운다. 누르는 순간 치우면
        # 끌지 않고 고르기만 해도 사라진다.
        self.bar.hide_bar()
        change = drag.update(self.figure, d, event.x, event.y)
        if change is None:
            return
        # 끌기 도중에는 히스토리에 쌓지 않는다. 마우스 이동마다 한 칸씩
        # 쌓이면 실행 취소 한 번이 1픽셀을 되돌리게 된다.
        self.win.session.set_prop(change.path, change.prop, change.value,
                                  record=False)
        self.draw_idle()
        self.win.status(f"{change.path}.{change.prop} = "
                        f"{[round(v, 3) for v in change.value]}")

    def _release(self, event):
        if self._pending is not None:
            target, x0, y0 = self._pending
            self._pending = None
            self._open_editor(target, _at(event, x0, y0))
            return
        if self._drag is None:
            return
        d, before, extras = self._drag
        self._drag = None
        if not d.moved:
            return
        # 끌기 한 번이 실행 취소 한 칸이다
        prop = "bbox_to_anchor" if d.kind == "legend" else "position"
        after = self.win.session.recorded_value(d.path, prop)
        extras += self._grow_paper()
        self.win.session.history.push(
            Command(d.path, prop, before, after, extra=extras))
        self.win.after_edit("fig" if extras else d.path)
        # 끌기가 끝났으니 막대를 다시 내준다 — 이어서 손볼 것이 있게 마련이다
        if self._target is not None:
            self._show_bar(self._target, event)

    # 종이를 키우면 matplotlib이 제목·눈금 배치를 다시 계산해서 필요한
    # 크기가 조금 달라진다. 한 번으로는 몇 mm가 모자라 글자가 잘린 채 남는다.
    GROW_PASSES = 3

    def _grow_paper(self) -> list:
        """종이를 내용에 맞춘다 (필요하면 키우고, 남으면 줄인다).

        같은 끌기에 딸린 변경으로 묶는다. 따로 쌓으면 실행 취소 한 번이
        축은 되돌리고 종이는 그대로 두어 그림이 어긋난 채 남는다.
        """
        out = []
        for _ in range(self.GROW_PASSES):
            g = layout.fit_to_content(self.figure)
            if g is None:
                break
            for path, prop, value in g.changes():
                was = self.win.session.spec.of(path).get(prop)
                self.win.session.set_prop(path, prop, value, record=False)
                # 같은 속성을 두 번 키웠으면 처음 값이 진짜 '이전'이다
                if not any(c.path == path and c.prop == prop for c in out):
                    out.append(Command(path, prop, was, value))
                else:
                    next(c for c in out
                         if c.path == path and c.prop == prop).new = value
            # 다시 재려면 새 크기의 표시 배율로 그려져 있어야 한다. 배율을
            # 맞추지 않고 재면 display 픽셀과 인치의 환산이 어긋나 몇 mm가
            # 모자란 채로 수렴한 것처럼 보인다.
            self.win.canvas_frame.fit()
            self.draw()
        else:
            # 정해진 횟수를 다 쓰고도 남았다 — 진동하거나 아주 느리게 수렴하는
            # 경우다. 종이가 몇 mm 모자란 채 남고 글자가 잘릴 수 있다.
            # 조용히 끝내면 사용자는 이것이 최종 상태인지 도구가 포기한
            # 상태인지 구분할 수 없다.
            if layout.fit_to_content(self.figure) is not None:
                self.win.status(_t(
                    "종이를 내용에 맞추지 못했습니다 ({n}번 시도). "
                    "글자가 잘려 보이면 크기를 직접 조절하세요.",
                    n=self.GROW_PASSES))
        return out


class ViewToolbar(NavToolbar):
    """확대·이동 도구. 뒤로/앞으로/홈은 **보기만** 되돌린다.

    matplotlib의 기본 구현은 뷰 한계와 함께 **축 위치까지** 스택에 담았다가
    함께 되돌린다(NavigationToolbar2.push_current / _update_view). 그래서
    툴바의 뒤로가기가 figtune으로 옮겨둔 축 상자를 화면에서만 슬쩍 되돌리고,
    spec은 그대로 남아 화면과 코드가 어긋난다.

    배치는 figtune의 것이고 실행 취소로 되돌린다. 툴바는 보기만 맡는다 —
    두 히스토리가 같은 상태를 놓고 다투지 않아야 한다.
    """

    # 확대·이동이 끝났다. spec이 화면을 따라가야 내보낸 그림과 생성 코드가
    # 어긋나지 않는다.
    view_changed = Signal()

    def _update_view(self):
        nav = self._nav_stack()
        if nav is None:
            return
        try:
            for ax, (view, _positions) in list(nav.items()):
                ax._set_view(view)
        except (TypeError, ValueError):     # pragma: no cover - 구조가 바뀌면
            super()._update_view()          # 기본 동작으로 물러선다
        self.canvas.draw_idle()
        self.view_changed.emit()

    def push_current(self):
        super().push_current()
        self.view_changed.emit()


class MainWindow(QMainWindow):
    def __init__(self, script: str | Path, python: str | None = None,
                 spec_in=None, spec_out=None, png_out=None, dpi: int = 300):
        super().__init__()
        self._current: str | None = None      # 지금 고른 selector
        # spec_out/png_out은 PowerPoint 애드인이 결과를 회수하는 경로다.
        self.spec_out, self.png_out, self.export_dpi = spec_out, png_out, dpi
        self.session = Session(python=python)
        from ...core.spec import Spec
        report = self.session.open(
            script, spec=Spec.load(spec_in) if spec_in else None)

        self.setWindowTitle(f"figtune — {Path(script).name}")
        self.resize(1360, 840)

        self.canvas = Canvas(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([_t("요소")])
        self.tree.itemSelectionChanged.connect(self._tree_selected)

        self.inspector = Inspector()
        self.inspector.edited.connect(self._on_edit)
        self.inspector.reset.connect(self._on_reset)

        self.code = QPlainTextEdit()
        self.code.setReadOnly(True)
        self.code.setStyleSheet("font-family: monospace; font-size: 11px;")

        right = QTabWidget()
        right.addTab(self.inspector, _t("속성"))
        right.addTab(self.code, _t("코드"))
        right.currentChanged.connect(
            lambda i: self._refresh_code() if i == 1 else None)
        self.right = right

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.tree)
        self.btn_labels = QPushButton(_t("패널 라벨 (a)(b)(c) 일괄 삽입"))
        self.btn_labels.clicked.connect(self._add_panel_labels)
        lv.addWidget(self.btn_labels)
        self.btn_text = QPushButton(_t("선택한 축에 텍스트 추가"))
        self.btn_text.clicked.connect(self._add_text)
        lv.addWidget(self.btn_text)

        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        self.canvas_frame = CanvasFrame(self.canvas)
        self.toolbar = ViewToolbar(self.canvas, self)
        # 확대·이동은 관찰 도구다. spec을 자동으로 건드리지 않고 알리기만
        # 한다 — 남길지는 사용자가 메뉴에서 정한다.
        self.toolbar.view_changed.connect(self._view_changed)
        # 확대는 툴바에서 한다. 그 결과를 남기는 버튼도 같은 자리에 있어야
        # 찾는다 — 메뉴에만 두면 확대해 놓고 어디서 남기는지 모른다.
        self.toolbar.addSeparator()
        self.apply_view_act = self.toolbar.addAction(
            _t("범위 적용"), self.apply_view_to_spec)
        self.apply_view_act.setEnabled(False)
        cv.addWidget(self.toolbar)
        cv.addWidget(self.canvas_frame, 1)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(center)
        split.addWidget(right)
        split.setSizes([260, 720, 380])
        self.setCentralWidget(split)

        self.setStatusBar(QStatusBar())
        self._build_menu()
        self.reload_tree()
        self.capture_view_baseline()
        self.sync_view_action()
        self._report_issues(report)

    # --- 메뉴 ------------------------------------------------------------

    def _build_menu(self):
        m = self.menuBar().addMenu(_t("파일"))
        self._act(m, _t("저장"), "Ctrl+S", self.save)
        self._act(m, _t("스크립트 재실행"), "Ctrl+R", self.reload_script)
        m.addSeparator()
        self._act(m, _t("내보내기…"), "Ctrl+E", self.export)

        e = self.menuBar().addMenu(_t("편집"))
        self._act(e, _t("실행 취소"), QKeySequence.Undo, self.undo)
        self._act(e, _t("다시 실행"), QKeySequence.Redo, self.redo)
        e.addSeparator()
        self._act(e, _t("현재 보기를 축 범위로"), "Ctrl+Shift+L",
                  self.apply_view_to_spec)

        # 언어 이름은 늘 그 언어로 적는다. 읽을 수 없는 언어에 갇혔을 때
        # 빠져나올 길이 되어야 하기 때문이다.
        g = self.menuBar().addMenu(_t("언어"))
        current = i18n.saved_language()
        for code, name in (("ko", "한국어"), ("en", "English"),
                           (None, _t("시스템 따름"))):
            a = self._act(g, name, None,
                          lambda _=False, c=code: self.set_language(c))
            a.setCheckable(True)
            a.setChecked(current == code)

    def _act(self, menu, text, shortcut, slot):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    # --- 트리 ------------------------------------------------------------

    def reload_tree(self):
        self.session.refresh_tree()
        self.tree.clear()

        def add(node, parent):
            item = QTreeWidgetItem([node.label])
            item.setData(0, Qt.UserRole, node.path if node.kind != "group" else None)
            (parent.addChild(item) if parent else
             self.tree.addTopLevelItem(item))
            for c in node.children:
                add(c, item)
            return item

        root = add(self.session.tree, None)
        root.setExpanded(True)
        for i in range(root.childCount()):
            root.child(i).setExpanded(True)

    def _tree_selected(self):
        items = self.tree.selectedItems()
        if not items:
            return
        path = items[0].data(0, Qt.UserRole)
        if path:
            self.select(path, from_tree=True)

    # --- 선택 / 편집 -----------------------------------------------------

    def select(self, path: str | None, from_tree: bool = False):
        self._current = path
        self.canvas.set_highlight(
            path, getattr(self.canvas, "_target", None)
            if not from_tree else None)
        if path is None:
            self.inspector.show_path(None, {}, set())
            self.canvas.bar.hide_bar()
            return
        vals = self.session.values(path)
        over = {n for n in self.session.spec.of(path)}
        if sel.parse(path).kind == "usertext":
            over = set(vals)
        self.inspector.show_path(path, vals, over)
        self.status(path)
        if not from_tree:
            self._sync_tree_selection(path)

    def has_selection(self) -> bool:
        return bool(getattr(self, "_current", None)) or self.canvas.bar.shown

    def clear_selection(self):
        """고른 것을 놓는다 — 막대·테두리·트리 표시가 함께 사라진다.

        하나만 지우면 화면마다 다른 것을 고른 것처럼 보인다.
        """
        self.tree.blockSignals(True)
        self.tree.clearSelection()
        self.tree.setCurrentItem(None)
        self.tree.blockSignals(False)
        self.canvas._target = None
        self.select(None)
        self.canvas.setFocus()
        self.status(_t("선택 해제"))

    def _sync_tree_selection(self, path):
        it = self.tree.findItems("", Qt.MatchContains | Qt.MatchRecursive, 0)
        for item in it:
            if item.data(0, Qt.UserRole) == path:
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(item)
                self.tree.blockSignals(False)
                return

    def _on_edit(self, path, name, value):
        try:
            self.session.set_prop(path, name, value)
        except Exception as exc:
            self.status(_t("적용 실패: {err}", err=exc))
            return
        if path == "fig" and name == "size_inches":
            self.canvas_frame.fit()
        self.canvas.draw_idle()
        self.mark_dirty()
        self.refresh_overlays()
        if self.right.currentIndex() == 1:
            self._refresh_code()

    def _on_reset(self, path, name):
        self.session.reset_prop(path, name)
        self.status(_t("{path}.{name} override 제거됨 — 재실행하면 "
                       "원래값으로 돌아갑니다", path=path, name=name))
        self.mark_dirty()

    def refresh_overlays(self):
        """미니 툴바와 대화상자가 열려 있으면 값을 맞춘다.

        같은 값을 세 곳이 보여주므로, 한 곳에서 고친 뒤 나머지가 옛 값을
        들고 있으면 다음 조작이 그 옛 값으로 되돌린다.
        """
        bar = self.canvas.bar
        if bar.shown and bar.path:
            bar.refresh(self.session.values(bar.path))
        dlg = getattr(self.canvas, "_dialog", None)
        if dlg is not None:
            dlg.refresh(self.session.values)

    def refresh_inspector(self):
        if getattr(self, "_current", None):
            self.inspector.refresh_values(self.session.values(self._current))

    # --- 보기(확대·이동) -------------------------------------------------

    def capture_view_baseline(self):
        """스크립트가 낸 보기를 기억한다.

        기준선이 없으면 툴바가 처음 스택을 채울 때의 값까지 '바뀐 것'으로
        보고 override를 만든다. 손대지 않은 그림에 xlim이 생기면 '명시된
        키만 override'라는 원칙이 깨진다.
        """
        self._view_baseline = {
            sel.axes(i): {"xlim": [float(v) for v in ax.get_xlim()],
                          "ylim": [float(v) for v in ax.get_ylim()]}
            for i, ax in enumerate(self.session.fig.axes)}

    def _view_changes(self) -> list:
        """지금 보는 범위 중 spec에 적힌 것과 다른 것들.

        (path, prop, 이전값, 지금값) 목록. 스크립트가 낸 그대로인 축은
        빠진다 — 손대지 않은 그림에 xlim이 생기면 '명시된 키만 override'가
        깨진다.
        """
        base = getattr(self, "_view_baseline", None)
        if not base:
            return []
        out = []
        for i, ax in enumerate(self.session.fig.axes):
            path = sel.axes(i)
            for prop, getter in (("xlim", ax.get_xlim), ("ylim", ax.get_ylim)):
                now = [round(float(v), 6) for v in getter()]
                was = self.session.spec.of(path).get(prop)
                if was is None:
                    was_or_base = [round(v, 6)
                                   for v in base.get(path, {}).get(prop, [])]
                else:
                    was_or_base = [round(v, 6) for v in was]
                if now == was_or_base:
                    continue
                out.append((path, prop, was, now))
        return out

    def view_differs(self) -> bool:
        """보고 있는 범위가 spec과 다른가."""
        return bool(self._view_changes())

    def sync_view_action(self):
        """지금 남길 것이 있을 때만 버튼을 켠다."""
        act = getattr(self, "apply_view_act", None)
        if act is None:
            return
        on = self.view_differs()
        act.setEnabled(on)
        act.setText(_t("범위 적용"))
        act.setToolTip(
            _t("지금 보는 확대·이동 범위를 축 범위(xlim/ylim)로 남깁니다.")
            if on else _t("보기가 축 범위와 같습니다."))

    def _view_changed(self):
        """관찰 도구가 보기를 바꿨다. spec은 건드리지 않고 알리기만 한다."""
        self.sync_view_action()
        if self.view_differs():
            self.status(_t("확대·이동은 보기만 바꿉니다. 남기려면 "
                           "편집 › 현재 보기를 축 범위로."))

    def apply_view_to_spec(self):
        """지금 보는 범위를 축 범위(xlim/ylim)로 남긴다.

        확대·이동은 관찰 도구다. 자동으로 spec에 넣으면 잠깐 둘러본 것까지
        기록되고, 두 히스토리가 같은 상태를 놓고 다투게 된다. 남길지는
        사용자가 정한다.
        """
        changes = self._view_changes()
        if not changes:
            self.status(_t("보기가 축 범위와 같습니다."))
            return
        self.session.history.seal()
        cmds = []
        for path, prop, was, now in changes:
            self.session.set_prop(path, prop, now, record=False)
            cmds.append(Command(path, prop, was, now))
        # 한 번 적용이 실행 취소 한 칸이다 (패널이 여럿이어도)
        self.session.history.push(
            Command(cmds[0].path, cmds[0].prop, cmds[0].old, cmds[0].new,
                    extra=cmds[1:]))
        self.mark_dirty()
        self.refresh_inspector()
        self.refresh_overlays()
        if self.right.currentIndex() == 1:
            self._refresh_code()
        self.sync_view_action()
        self.status(_t("보기를 축 범위로 적용했습니다 ({n}건)",
                       n=len(changes)))

    @contextmanager
    def spec_view(self):
        """내보내는 동안만 spec에 적힌 범위로 되돌린다.

        관찰용 확대를 그대로 내보내면 그림에는 확대가 들어가는데 생성 코드에는
        없어, 'GUI 렌더와 코드 실행 결과가 같다'는 보장이 깨진다. 확대를
        남기고 싶으면 먼저 축 범위로 적용해야 한다.
        """
        changes = self._view_changes()
        if not changes:
            yield False
            return
        saved = [(ax, list(ax.get_xlim()), list(ax.get_ylim()))
                 for ax in self.session.fig.axes]
        base = self._view_baseline
        for i, ax in enumerate(self.session.fig.axes):
            path = sel.axes(i)
            for prop, setter in (("xlim", ax.set_xlim), ("ylim", ax.set_ylim)):
                want = self.session.spec.of(path).get(prop) \
                    or base.get(path, {}).get(prop)
                if want:
                    setter(want)
        try:
            yield True
        finally:
            for ax, xl, yl in saved:
                ax.set_xlim(xl)
                ax.set_ylim(yl)
            self.canvas.draw_idle()

    def after_edit(self, path: str | None = None):
        """캔버스에서 직접 고친 뒤 나머지 화면을 맞춘다."""
        self.mark_dirty()
        self.refresh_inspector()
        self.refresh_overlays()
        self.sync_view_action()
        if path == "fig":
            self.canvas_frame.fit()
        if self.right.currentIndex() == 1:
            self._refresh_code()

    # --- 동작 ------------------------------------------------------------

    def _add_panel_labels(self):
        self.session.add_panel_labels()
        self.canvas.draw_idle()
        self.reload_tree()
        self.mark_dirty()

    def _add_text(self):
        path = getattr(self, "_current", None)
        ax_i = sel.parse(path).axes if path else 0
        if ax_i is None:
            ax_i = 0
        text, ok = QInputDialog.getText(self, _t("텍스트 추가"), _t("내용:"))
        if not ok or not text:
            return
        tid = self.session.add_text(ax_i, text)
        self.canvas.draw_idle()
        self.reload_tree()
        self.select(sel.usertext(ax_i, tid))
        self.mark_dirty()

    def undo(self):
        cmd = self.session.history.undo()
        if cmd:
            self.canvas.draw_idle()
            self.refresh_inspector()
            self.sync_view_action()
            self.status(_t("실행 취소: {what}", what=cmd.describe()))

    def redo(self):
        cmd = self.session.history.redo()
        if cmd:
            self.canvas.draw_idle()
            self.refresh_inspector()
            self.sync_view_action()
            self.status(_t("다시 실행: {what}", what=cmd.describe()))

    def save(self):
        hook = False
        if self.session.script and self.session.style_path:
            src = self.session.script.read_text(encoding="utf-8")
            if "apply_style" not in src:
                ans = QMessageBox.question(
                    self, _t("원본 스크립트 수정"),
                    _t("{name}에 import/호출 2줄을 추가할까요?\n"
                       "figtune이 원본 파일을 만지는 유일한 지점입니다.\n"
                       "거절해도 스타일 파일은 저장됩니다.",
                       name=self.session.script.name))
                hook = ans == QMessageBox.Yes
        with self.spec_view():
            out = self.session.save(install_hook=hook)
        # 호출자(PowerPoint 애드인 등)가 지정한 경로에도 결과를 남긴다
        if self.spec_out:
            self.session.spec.dump(self.spec_out)
        if self.png_out:
            self.session.export(self.png_out, dpi=self.export_dpi)
        self.status(_t("저장됨 — {style}, {spec}",
                       style=Path(out["style"]).name,
                       spec=Path(out["spec"]).name))
        self.setWindowTitle(self.windowTitle().rstrip(" *"))
        self._refresh_code()

    def reload_script(self):
        rep = self.session.reload()
        self.canvas.figure = self.session.fig
        self.canvas.draw_idle()
        self.reload_tree()
        self.capture_view_baseline()
        self._report_issues(rep)

    def export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, _t("내보내기"), "figure.pdf",
            "PDF (*.pdf);;PNG (*.png);;SVG (*.svg)")
        if not path:
            return
        dpi, ok = QInputDialog.getInt(self, "DPI", _t("해상도:"),
                                      300, 50, 1200, 50)
        if not ok:
            return
        with self.spec_view() as restored:
            self.session.export(path, dpi=dpi)
        self.status(_t("내보냄: {path}", path=path) if not restored else
                    _t("내보냄: {path} — 화면의 확대는 빼고 코드와 같은 "
                       "그림으로 내보냈습니다.", path=path))

    # --- 알림 ------------------------------------------------------------

    def _refresh_code(self):
        try:
            src = self.session.preview_code()
        except Exception as exc:
            self.code.setPlainText(_t("# 코드 생성 실패: {err}", err=exc))
            return
        self.code.setPlainText(src)
        # 헤더와 헬퍼는 늘 같다. 사용자가 볼 것은 자기 편집이 들어간
        # apply_style 본문이므로 거기로 스크롤한다.
        lines = src.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("def apply_style"):
                cur = self.code.textCursor()
                cur.movePosition(cur.MoveOperation.Start)
                cur.movePosition(cur.MoveOperation.Down,
                                 cur.MoveMode.MoveAnchor, i)
                self.code.setTextCursor(cur)
                self.code.centerCursor()
                bar = self.code.verticalScrollBar()
                bar.setValue(min(bar.maximum(), bar.value() + 6))
                break

    def mark_dirty(self):
        if not self.windowTitle().endswith("*"):
            self.setWindowTitle(self.windowTitle() + " *")

    def status(self, msg: str):
        self.statusBar().showMessage(msg, 6000)

    def _report_issues(self, rep):
        msgs = []
        dc = getattr(rep, "data_changed", None) or {}
        moved = dc.get("changed", []) + dc.get("added", []) + dc.get("removed", [])
        if moved:
            msgs.append(_t("입력 데이터가 바뀌었습니다: {names}\n"
                           "그림이 달라지는 것은 정상입니다.",
                           names=", ".join(Path(p).name for p in moved[:5])))
        if rep.stale:
            lines = "\n".join(
                _t("  · {path}  → 재매칭 제안: {suggest}",
                   path=p, suggest=i["suggest"] or _t("없음"))
                for p, i in sorted(rep.stale.items()))
            if moved:
                # 데이터가 바뀌었으면 지문 불일치는 예상된 결과다.
                # 같은 경고를 띄우면 진짜 위험한 경우를 무시하게 된다.
                msgs.append(_t("아래 항목의 지문이 달라졌으나, 데이터 변경으로 "
                               "설명됩니다:\n{lines}", lines=lines))
            else:
                msgs.append(_t("원본 스크립트가 변경되었습니다. 아래 항목은 다른 "
                               "대상을 가리키고 있을 수 있습니다:\n{lines}",
                               lines=lines))
        if rep.style_readonly:
            msgs.append(_t("스타일 모듈이 수동 편집되어 GUI로 되읽을 수 없습니다. "
                           "저장하면 덮어씁니다.\n  {issues}",
                           issues="\n  ".join(rep.style_issues[:6])))
        if rep.apply_failures:
            msgs.append(_t("일부 override 적용 실패:\n  {failures}",
                           failures="\n  ".join(
                               f"{p}.{n}: {w}"
                               for p, n, w in rep.apply_failures[:6])))
        if msgs:
            QMessageBox.warning(self, _t("확인 필요"), "\n\n".join(msgs))

    # --- 언어 ------------------------------------------------------------

    def set_language(self, lang: str | None):
        """lang이 None이면 '시스템 따름'으로 되돌린다."""
        target = i18n.resolve_language(lang)
        if target == "ko" and not fonts.can_render():
            # 한국어로 바꿔주면 메뉴까지 네모가 되어 되돌릴 길이 막힌다.
            self._font_dialog(switched=False)
            self._build_menu_refresh()
            return
        i18n.save_language(lang)
        i18n.set_language(target)
        self.retranslate()

    def retranslate(self):
        """언어를 바꾼 뒤 화면의 모든 글자를 다시 붙인다."""
        self.tree.setHeaderLabels([_t("요소")])
        self.right.setTabText(0, _t("속성"))
        self.right.setTabText(1, _t("코드"))
        self.btn_labels.setText(_t("패널 라벨 (a)(b)(c) 일괄 삽입"))
        self.btn_text.setText(_t("선택한 축에 텍스트 추가"))
        self.inspector.retranslate()
        self.sync_view_action()
        self._build_menu_refresh()
        self.reload_tree()          # 트리 라벨에도 번역 대상이 있다
        current = getattr(self, "_current", None)
        self.select(current) if current else self.inspector.show_path(
            None, {}, set())

    def _build_menu_refresh(self):
        self.menuBar().clear()
        self._build_menu()

    def warn_no_hangul_font(self):
        """시작 시 한국어에서 영어로 내려앉았을 때 한 번만 알린다."""
        if config.get("font_notice_dismissed"):
            return
        self._font_dialog(switched=True)

    def _font_dialog(self, switched: bool):
        cmd = fonts.install_command()
        body = [_t("이 환경에는 한글 글꼴이 없어 한국어 글자가 네모로 표시됩니다.")]
        body.append(_t("그래서 화면을 영어로 표시했습니다.") if switched
                    else _t("그래서 한국어로 바꾸지 않았습니다."))
        if cmd:
            body.append(_t("아래 명령으로 글꼴을 설치한 뒤 figtune을 다시 "
                           "실행하세요:\n\n  {cmd}", cmd=cmd))
        else:
            body.append(_t("시스템에 CJK 글꼴(예: Noto Sans CJK)을 설치한 뒤 "
                           "figtune을 다시 실행하세요."))

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(_t("한글 글꼴 없음"))
        box.setText("\n\n".join(body))
        box.setStandardButtons(QMessageBox.Ok)
        if switched:
            again = box.addButton(_t("다시 보지 않기"),
                                  QMessageBox.ActionRole)
        box.exec()
        if switched and box.clickedButton() is again:
            config.set("font_notice_dismissed", True)


def launch(script: str | Path, python: str | None = None, spec_in=None,
           spec_out=None, png_out=None, dpi: int = 300,
           lang: str | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    # 폰트 검사는 QApplication이 있어야 한다. 한국어인데 못 그리면 화면이
    # 통째로 네모가 되므로, 조용히 깨뜨리는 대신 영어로 내리고 알린다.
    downgraded = i18n.init(lang) == "ko" and not fonts.can_render()
    if downgraded:
        i18n.set_language("en")

    win = MainWindow(script, python=python, spec_in=spec_in,
                     spec_out=spec_out, png_out=png_out, dpi=dpi)
    win.show()
    if downgraded:
        win.warn_no_hangul_font()
    return app.exec()
