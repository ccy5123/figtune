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
from PySide6.QtWidgets import (QAbstractItemView,  # noqa: E402
                               QApplication, QDialog, QFileDialog,
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
from ...core import props as P  # noqa: E402
from ...core import selector as sel  # noqa: E402
from ...core.history import Command  # noqa: E402
from ...core.session import EXISTS, Session  # noqa: E402
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


def _adds_to_selection(event) -> bool:
    """Shift나 Ctrl을 누른 채인가.

    PowerPoint는 도형 선택에서 둘을 같게 다룬다 — 어느 쪽이든 토글-추가다.
    둘이 갈리는 것은 끌기(복제 vs 축 고정)와 목록에서이지 캔버스가 아니다.
    범위 선택은 목록인 트리가 맡는다.

    matplotlib은 키 상태를 자기 key_press 이벤트로만 갱신하므로, 캔버스가
    포커스를 갖기 전에 누른 수식키를 놓친다. Qt에 한 번 더 묻는다.
    """
    key = (getattr(event, "key", None) or "").lower()
    if "shift" in key or "control" in key or "ctrl" in key:
        return True
    mods = QApplication.keyboardModifiers()
    return bool(mods & (Qt.ShiftModifier | Qt.ControlModifier))


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

    def __init__(self, window: "MainWindow", figure=None):
        # figure를 명시로 받는다. window.session에서 꺼내면 문서를 만드는
        # 도중(아직 활성 탭이 아닐 때) 엉뚱한 문서의 figure를 집는다.
        super().__init__(figure if figure is not None else window.session.fig)
        self.win = window
        self._map = None            # hit.HitMap — 다시 그릴 때까지 유효
        self._drag = None           # (core.drag.Drag, 시작 override 값)
        self._pending = None        # 끌기인지 제자리 편집인지 아직 모른다
        self._kept_many = False     # 여럿을 고른 채로 눌렀는가
        self.editor = direct.InPlaceEditor(self)
        self.editor.committed.connect(self._commit_text)
        self.bar = MiniToolbar(self)
        self.bar.edited.connect(self._bar_edit)
        self.bar.more.connect(lambda: self.open_dialog(self._target))
        self._target = None         # 마지막으로 고른 대상 (대화상자·툴바용)
        self._highlight = []        # (path, x, y, w, h) Qt 좌표 — 화면에만 그린다
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
                                selected=self._sole_selection(),
                                artists=artists)

    def _sole_selection(self) -> str | None:
        """핸들을 내줄 대상. 여러 개를 골랐으면 없다.

        여러 개를 고른 채 핸들이 살아 있으면 무엇의 크기가 바뀔지 모호하다.
        """
        picked = self.win.selection()
        return picked[0] if len(picked) == 1 else None

    # --- 클릭 -------------------------------------------------------------

    def viewing(self) -> bool:
        """툴바의 확대·이동이 켜져 있는가.

        관찰 도구와 편집은 완전히 별개다. 켜져 있는 동안 편집 제스처를
        함께 처리하면, 들여다보려고 끈 것만으로 축이 옮겨져 spec이 바뀐다.
        """
        return bool(getattr(self.win.toolbar, "mode", ""))

    def _press(self, event):
        if event.button != 1 or self.viewing():
            return
        if self.editor.active:
            self.editor.commit()        # 다른 곳을 누르면 확정된다

        targets = self.targets_at(event)
        target = self._disambiguate(targets)
        if target is None:
            return

        self._target = target
        if _adds_to_selection(event):
            # 고르기만 한다. 더하려고 누른 것이지 옮기거나 고치려는 것이 아니다.
            self.win.toggle_path(target.path)
            return
        # 이미 고른 것들 중 하나를 누른 것이면 선택을 유지한다. 여기서
        # 하나로 줄이면 함께 옮기려던 것이 잡은 것 하나만 움직인다.
        # 움직이지 않고 떼면 그때 하나로 줄인다 — PowerPoint와 같다.
        picked = self.win.selection()
        self._kept_many = target.path in picked and len(picked) > 1
        if not self._kept_many:
            self.win.select(target.path)
        if event.dblclick:
            self.open_dialog(target)
            return
        if not self._kept_many:
            # 여럿을 고른 채로는 막대를 내지 않는다. 막대는 하나를 고치는
            # 도구라, 인스펙터가 전부를 고치는 동안 옆에 있으면 어느 쪽이
            # 적용되는지 알 수 없다.
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

    def set_highlight(self, paths, target=None):
        """고른 대상마다 테두리를 친다.

        Qt로 그린다. matplotlib artist로 그리면 내보낸 그림에까지 테두리가
        따라 들어간다.

        하나만 그리면 여러 개를 고른 채로 무엇이 고쳐질지 알 수 없다.
        """
        if isinstance(paths, str) or paths is None:
            paths = [paths] if paths else []
        self._highlight_paths = list(paths)
        # 캔버스에서 고른 것이면 대상을 함께 기억한다. 트리에서 고른 경우는
        # 대상이 없으므로 path로만 맞춘다(축은 조금 넓게 잡힌다).
        self._highlight_target = target
        self._recompute_highlight()
        self.update()

    def highlights(self) -> list:
        return list(getattr(self, "_highlight", []) or [])

    def _box_for(self, path):
        target = getattr(self, "_highlight_target", None)
        # 기준(마지막) 대상에만 캔버스에서 잡은 target을 쓴다. 다른 것에
        # 갖다 붙이면 엉뚱한 상자가 나온다.
        if target is not None and target.path != path:
            target = None
        box = self.hitmap().bbox_of(path, target)
        return box if box is not None else self._artist_box(path)

    def _recompute_highlight(self):
        self._highlight = []
        dpr = getattr(self, "device_pixel_ratio", 1) or 1
        for path in getattr(self, "_highlight_paths", []):
            box = self._box_for(path)
            if box is None:
                continue
            x0, y0, x1, y1 = box
            self._highlight.append(
                (path, x0 / dpr, self.height() - y1 / dpr,
                 (x1 - x0) / dpr, (y1 - y0) / dpr))

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
        boxes = self.highlights()
        if not boxes:
            return
        painter = QPainter(self)
        pen = QPen(QColor("#2c7be5"))
        pen.setWidth(1)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        for _path, x, y, w, h in boxes:
            painter.drawRect(int(x) - 2, int(y) - 2, int(w) + 4, int(h) + 4)
        # 핸들은 하나만 골랐을 때만. 여러 개에 붙으면 무엇의 크기가 바뀌는지
        # 모호하고, 겹친 상자들 위에서 어느 것을 잡았는지도 알 수 없다.
        if len(boxes) == 1:
            path, x, y, w, h = boxes[0]
            if sel.parse(path).kind == "axes":
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

    @staticmethod
    def _moved_prop(d) -> str:
        return "bbox_to_anchor" if d.kind == "legend" else "position"

    def _drag_targets(self, target):
        """이 끌기가 옮길 것들. 잡은 것이 먼저다.

        잡은 것이 이미 고른 것들 중 하나면 나머지도 함께 따라온다 —
        PowerPoint와 같다. 하나만 움직이면 여러 개를 고른 것이 무의미해지고
        나머지를 같은 거리만큼 손으로 맞춰야 한다.

        고르지 않은 것을 잡았을 때는 그것 하나다. 이때는 _press가 이미
        선택을 그것으로 바꿔 두었다.
        """
        out = [target]
        picked = self.win.selection()
        if len(picked) > 1 and target.path in picked:
            for path in picked:
                if path == target.path:
                    continue
                t = hit.target_for_path(self.figure, path)
                if t is not None:
                    out.append(t)
        return out

    def _start_drag(self, target, event):
        drags, extras = [], []
        for t in self._drag_targets(target):
            d, pins = drag.begin(self.figure, t, event.x, event.y)
            if d is None:
                continue
            # 끌기에 딸린 확정값(범례 loc 등)은 히스토리에 따로 쌓지 않는다.
            # 따로 쌓으면 끌기 한 번을 되돌리는 데 실행 취소가 두 번 든다.
            for pin in pins:
                was = self.win.session.spec.of(pin.path).get(pin.prop)
                self.win.session.set_prop(pin.path, pin.prop, pin.value,
                                          record=False)
                extras.append(Command(pin.path, pin.prop, was, pin.value))
            drags.append(d)
        if not drags:
            return
        # 직전 편집과 한 칸으로 합쳐지면 실행 취소가 둘을 한꺼번에 되돌린다
        self.win.session.history.seal()
        befores = [self.win.session.recorded_value(d.path, self._moved_prop(d))
                   for d in drags]
        self._drag = (drags, befores, extras)

    def _motion(self, event):
        if self.viewing():
            # 확대·이동 중에는 툴바가 자기 커서를 쓴다. 여기서 덮으면
            # 편집할 수 있는 것처럼 보이는데 실제로는 아무 일도 없다.
            return
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
                self.hitmap().cursor(event.x, event.y,
                                     selected=self._sole_selection()),
                Qt.ArrowCursor))

    def _drag_to(self, event):
        drags = self._drag[0]
        # 실제로 움직이기 시작했을 때만 막대를 치운다. 누르는 순간 치우면
        # 끌지 않고 고르기만 해도 사라진다.
        self.bar.hide_bar()
        last = None
        for d in drags:
            # 각자 자기 좌표계에서 같은 커서 이동을 잰다. 대상마다 단위가
            # 달라도(축은 figure 비율, 텍스트는 축 좌표) 화면에서 간 거리는
            # 같아진다.
            change = drag.update(self.figure, d, event.x, event.y)
            if change is None:
                continue
            # 끌기 도중에는 히스토리에 쌓지 않는다. 마우스 이동마다 한 칸씩
            # 쌓이면 실행 취소 한 번이 1픽셀을 되돌리게 된다.
            self.win.session.set_prop(change.path, change.prop, change.value,
                                      record=False)
            last = change
        if last is None:
            return
        self.draw_idle()
        self.win.status(
            f"{last.path}.{last.prop} = {[round(v, 3) for v in last.value]}"
            if len(drags) == 1 else _t("{n}개 이동 중", n=len(drags)))

    def _collapse_to_pressed(self):
        """움직이지 않고 뗐다 — 여럿 중 누른 하나만 고른 것으로 본다.

        이것이 없으면 여러 개를 고른 뒤 그중 하나를 눌러도 선택이 그대로라
        하나만 고치려는 사용자가 빠져나올 길이 없다.
        """
        if self._kept_many and self._target is not None:
            self.win.select(self._target.path)
        self._kept_many = False

    def _release(self, event):
        if self._pending is not None:
            target, x0, y0 = self._pending
            self._pending = None
            self._collapse_to_pressed()
            self._open_editor(target, _at(event, x0, y0))
            return
        if self._drag is None:
            self._collapse_to_pressed()
            return
        drags, befores, extras = self._drag
        self._drag = None
        if not any(d.moved for d in drags):
            self._collapse_to_pressed()
            return
        self._kept_many = False
        # 끌기 한 번이 실행 취소 한 칸이다 — 옮긴 것이 몇 개든.
        cmds = []
        for d, before in zip(drags, befores):
            prop = self._moved_prop(d)
            cmds.append(Command(d.path, prop, before,
                                self.win.session.recorded_value(d.path, prop)))
        extras = cmds[1:] + extras + self._grow_paper()
        head = cmds[0]
        self.win.session.history.push(
            Command(head.path, head.prop, head.old, head.new, extra=extras))
        self.win.after_edit("fig" if extras else head.path)
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


class Document(QWidget):
    """열려 있는 스크립트 하나.

    문서마다 따로 가져야 하는 것을 여기 모은다 — 세션(과 그 안의 실행 취소),
    캔버스, 보기 도구, 선택, 보기 기준선. 창이 이것들을 직접 들고 있으면
    A 탭에서 고른 것이 B 탭에 적용되는 종류의 사고가 난다.

    트리와 인스펙터는 여기 없다. 지금 보고 있는 문서를 비추는 창의 것이다.
    """

    def __init__(self, window: "MainWindow", script, python=None, spec_in=None):
        super().__init__()
        self.session = Session(python=python)
        from ...core.spec import Spec
        self.report = self.session.open(
            script, spec=Spec.load(spec_in) if spec_in else None)

        # 고른 selector들. 마지막 것이 '기준' — 핸들과 미니 툴바가 그것을
        # 따르고, 트리와 캔버스가 같은 것을 가리키게 한다.
        self.selection: list[str] = []
        self.view_baseline: dict = {}
        self.dirty = False

        self.canvas = Canvas(window, self.session.fig)
        self.canvas_frame = CanvasFrame(self.canvas)
        self.toolbar = ViewToolbar(self.canvas, window)
        # 확대·이동은 관찰 도구다. spec을 자동으로 건드리지 않고 알리기만
        # 한다 — 남길지는 사용자가 메뉴에서 정한다.
        self.toolbar.view_changed.connect(window._view_changed)
        # 확대는 툴바에서 한다. 그 결과를 남기는 버튼도 같은 자리에 있어야
        # 찾는다 — 메뉴에만 두면 확대해 놓고 어디서 남기는지 모른다.
        self.toolbar.addSeparator()
        self.apply_view_act = self.toolbar.addAction(
            _t("범위 적용"), window.apply_view_to_spec)
        self.apply_view_act.setEnabled(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toolbar)
        lay.addWidget(self.canvas_frame, 1)

    @property
    def name(self) -> str:
        return self.session.script.name if self.session.script else "?"


class MainWindow(QMainWindow):
    def __init__(self, script: str | Path, python: str | None = None,
                 spec_in=None, spec_out=None, png_out=None, dpi: int = 300):
        super().__init__()
        self._python = python
        # spec_out/png_out은 PowerPoint 애드인이 결과를 회수하는 경로다.
        self.spec_out, self.png_out, self.export_dpi = spec_out, png_out, dpi

        self.resize(1360, 840)
        self.docs = QTabWidget()
        self.docs.setTabsClosable(True)
        self.docs.setDocumentMode(True)
        self.docs.tabCloseRequested.connect(self.close_document)
        self.docs.currentChanged.connect(self._document_changed)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([_t("요소")])
        # 트리는 목록이다 — Shift 범위와 Ctrl 개별이 사는 곳이 여기다.
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
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

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.docs)
        split.addWidget(right)
        split.setSizes([260, 720, 380])
        self.setCentralWidget(split)

        self.setStatusBar(QStatusBar())
        self._build_menu()
        report = self.open_document(script, spec_in=spec_in).report
        self.reload_tree()
        self.capture_view_baseline()
        self.sync_view_action()
        self._report_issues(report)

    # --- 문서(탭) ---------------------------------------------------------
    #
    # 창은 '지금 보고 있는 문서'만 안다. session·canvas·toolbar 같은 이름을
    # 속성으로 넘겨주므로, 문서 하나를 전제하던 코드가 그대로 동작한다.

    @property
    def doc(self) -> Document | None:
        return self.docs.currentWidget()

    def documents(self) -> list:
        return [self.docs.widget(i) for i in range(self.docs.count())]

    def document_count(self) -> int:
        return self.docs.count()

    def tab_label(self, index: int) -> str:
        return self.docs.tabText(index)

    @property
    def session(self):
        return self.doc.session

    @property
    def canvas(self):
        return self.doc.canvas

    @property
    def canvas_frame(self):
        return self.doc.canvas_frame

    @property
    def toolbar(self):
        return self.doc.toolbar

    @property
    def apply_view_act(self):
        return self.doc.apply_view_act

    @property
    def _selection(self) -> list:
        return self.doc.selection if self.doc is not None else []

    @_selection.setter
    def _selection(self, value):
        if self.doc is not None:
            self.doc.selection = list(value)

    @property
    def _view_baseline(self) -> dict:
        return self.doc.view_baseline if self.doc is not None else {}

    @_view_baseline.setter
    def _view_baseline(self, value):
        if self.doc is not None:
            self.doc.view_baseline = value

    def open_document(self, script, spec_in=None) -> Document:
        """스크립트를 새 탭으로 연다. 이미 열려 있으면 그 탭으로 간다.

        같은 파일이 두 탭에 있으면 어느 쪽 편집이 저장되는지 알 수 없다.
        """
        want = Path(script).resolve()
        for i, d in enumerate(self.documents()):
            if d.session.script == want:
                self.docs.setCurrentIndex(i)
                return d
        doc = Document(self, script, python=self._python, spec_in=spec_in)
        self.docs.addTab(doc, doc.name)
        self.docs.setCurrentWidget(doc)
        # 문서마다 자기 기준선이 필요하다. 없으면 그 탭에서는 보기 변화가
        # 잡히지 않아 '범위 적용'이 영영 켜지지 않는다.
        self.capture_view_baseline()
        self.sync_view_action()
        return doc

    def activate_document(self, index: int) -> None:
        self.docs.setCurrentIndex(index)

    def pick_merge_grid(self) -> tuple[int, int] | None:
        """몇 행 몇 열로 합칠지 고른다. 취소하면 None."""
        from .gridpicker import GridPickerPanel

        dlg = QDialog(self)
        dlg.setWindowTitle(_t("그림 합치기"))
        panel = GridPickerPanel(dlg)
        lay = QVBoxLayout(dlg)
        lay.addWidget(panel)
        # 훑다가 누르는 것으로 정해진다 — 확인 버튼을 한 번 더 누를 이유가 없다
        panel.picked.connect(lambda *_: dlg.accept())
        return panel.current() if dlg.exec() == QDialog.Accepted else None

    def merge_documents(self) -> None:
        """격자를 고르고, 칸을 채우고, 병합 결과를 새 탭으로 연다."""
        from .montagedialog import MontageDialog

        grid = self.pick_merge_grid()
        if grid is None:
            return
        dlg = MontageDialog(self, *grid)
        if dlg.exec() != QDialog.Accepted or dlg.result_path is None:
            return
        try:
            self._report_issues(self.open_document(dlg.result_path).report)
        except Exception as exc:
            self.status(_t("열지 못했습니다: {err}", err=exc))

    def open_dialog_file(self) -> None:
        start = str(self.session.script.parent) if self.session.script else ""
        path, _ = QFileDialog.getOpenFileName(
            self, _t("스크립트 열기"), start, "Python (*.py)")
        if not path:
            return
        try:
            self._report_issues(self.open_document(path).report)
        except Exception as exc:
            self.status(_t("열지 못했습니다: {err}", err=exc))

    def close_document(self, index: int) -> None:
        """탭을 닫는다. 마지막 하나는 닫지 않는다.

        빈 창은 아무것도 할 수 없는 상태다 — 들어갈 이유가 없다.
        """
        if self.docs.count() <= 1:
            return
        doc = self.docs.widget(index)
        self.docs.removeTab(index)
        doc.deleteLater()

    def _document_changed(self, _index: int) -> None:
        """탭이 바뀌었다. 창이 들고 있는 화면을 새 문서로 맞춘다."""
        if self.doc is None:
            return
        self.setWindowTitle(f"figtune — {self.doc.name}")
        self.reload_tree()
        self.select_paths(self.doc.selection)
        self.sync_view_action()
        if self.right.currentIndex() == 1:
            self._refresh_code()

    # --- 메뉴 ------------------------------------------------------------

    def _build_menu(self):
        m = self.menuBar().addMenu(_t("파일"))
        self._act(m, _t("열기…"), "Ctrl+O", self.open_dialog_file)
        self._act(m, _t("탭 닫기"), "Ctrl+W",
                  lambda: self.close_document(self.docs.currentIndex()))
        m.addSeparator()
        self._act(m, _t("저장"), "Ctrl+S", self.save)
        self._act(m, _t("스크립트 재실행"), "Ctrl+R", self.reload_script)
        m.addSeparator()
        self._act(m, _t("그림 합치기…"), "Ctrl+M", self.merge_documents)
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
        """트리에서 고른 것을 그대로 받는다.

        Shift 범위와 Ctrl 개별은 Qt가 처리한다 — 여기서는 결과만 읽는다.
        그룹 노드(path 없음)는 건너뛴다.
        """
        paths = [it.data(0, Qt.UserRole) for it in self.tree.selectedItems()]
        paths = [p for p in paths if p]
        if paths:
            self.select_paths(paths, from_tree=True)

    # --- 선택 / 편집 -----------------------------------------------------

    @property
    def _current(self) -> str | None:
        """기준 selector — 가장 마지막에 고른 것.

        핸들·미니 툴바·상태줄처럼 '하나'를 전제하는 곳이 이것을 본다.
        속성으로 두어 단일 선택을 전제하던 자리들이 그대로 동작한다.
        """
        return self._selection[-1] if self._selection else None

    def selection(self) -> list[str]:
        return list(self._selection)

    def select(self, path: str | None, from_tree: bool = False):
        self.select_paths([path] if path else [], from_tree=from_tree)

    def toggle_path(self, path: str, from_tree: bool = False):
        """PowerPoint의 Shift/Ctrl 클릭 — 있으면 빼고 없으면 더한다.

        뺄 방법이 없으면 잘못 고른 하나를 되돌리려고 처음부터 다시 골라야 한다.
        """
        picked = self.selection()
        if path in picked:
            picked.remove(path)
        else:
            picked.append(path)
        self.select_paths(picked, from_tree=from_tree)

    def select_paths(self, paths, from_tree: bool = False):
        seen, picked = set(), []
        for p in paths:
            if p and p not in seen:
                seen.add(p)
                picked.append(p)
        self._selection = picked
        self.canvas.set_highlight(
            picked, getattr(self.canvas, "_target", None)
            if not from_tree else None)
        if not picked:
            self.inspector.show([], {}, set())
            self.canvas.bar.hide_bar()
            return
        vals, mixed, over = self._shared_values(picked)
        self.inspector.show(picked, vals, over, mixed)
        self.status(picked[0] if len(picked) == 1
                    else _t("{n}개 선택됨", n=len(picked)))
        if not from_tree:
            self._sync_tree_selection(picked)

    def _shared_values(self, paths):
        """고른 것들의 (공통값, 값이 갈리는 속성, override된 속성).

        값이 갈리면 공통값을 지어내지 않는다. 아무 값이나 채우면 그것이 현재
        값인 줄 알고 넘어가서, 건드리지 않은 대상까지 그 값으로 덮인다.
        """
        per_path = {p: self.session.values(p) for p in paths}
        vals, mixed, over = {}, set(), set()
        for prop in P.common_props([sel.parse(p).kind for p in paths]):
            seen = [per_path[p].get(prop.name) for p in paths]
            if all(v == seen[0] for v in seen[1:]):
                vals[prop.name] = seen[0]
            else:
                mixed.add(prop.name)
            if any(self.session.is_overridden(p, prop.name) for p in paths):
                over.add(prop.name)
        return vals, mixed, over

    def has_selection(self) -> bool:
        return bool(self._selection) or self.canvas.bar.shown

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

    def _sync_tree_selection(self, paths):
        # 문자열 하나가 들어오면 글자 단위로 풀려 아무것도 안 맞는다.
        # 조용히 빈 선택이 되는 종류의 사고라 여기서 막는다.
        wanted = {paths} if isinstance(paths, str) else set(paths)
        items = self.tree.findItems("", Qt.MatchContains | Qt.MatchRecursive, 0)
        self.tree.blockSignals(True)
        self.tree.clearSelection()
        last = None
        for item in items:
            if item.data(0, Qt.UserRole) in wanted:
                item.setSelected(True)
                last = item
        if last is not None:
            self.tree.setCurrentItem(last)
        self.tree.blockSignals(False)

    def _on_edit(self, name, value):
        """인스펙터에서 고친 값을 고른 것 전부에 넣는다.

        인스펙터는 교집합만 보여주므로, 화면에 있는 것은 곧 전부에 적용된다.
        """
        paths = self.selection()
        if not paths:
            return
        try:
            self.session.set_props(paths, name, value)
        except Exception as exc:
            self.status(_t("적용 실패: {err}", err=exc))
            return
        if "fig" in paths and name == "size_inches":
            self.canvas_frame.fit()
        self.canvas.draw_idle()
        self.mark_dirty()
        self.refresh_overlays()
        if self.right.currentIndex() == 1:
            self._refresh_code()

    def _on_reset(self, name):
        paths = self.selection()
        for path in paths:
            self.session.reset_prop(path, name)
        if not paths:
            return
        self.status(_t("{path}.{name} override 제거됨 — 재실행하면 "
                       "원래값으로 돌아갑니다",
                       path=paths[0] if len(paths) == 1
                       else _t("{n}개 선택됨", n=len(paths)), name=name))
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
        """편집 뒤 값을 되읽는다. 여럿이면 공통값만 — 갈리는 칸은 비워 둔다."""
        picked = self.selection()
        if not picked:
            return
        vals, mixed, _over = self._shared_values(picked)
        self.inspector.refresh_values(
            {k: v for k, v in vals.items() if k not in mixed})

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

    @staticmethod
    def _changes_membership(cmd) -> bool:
        """이 커맨드가 요소를 만들거나 없앴는가.

        값만 바뀐 경우까지 트리를 다시 세우면 펼침 상태가 매번 접힌다.
        """
        return any(c.prop == EXISTS for c in [cmd, *cmd.extra])

    def undo(self):
        cmd = self.session.history.undo()
        if cmd:
            self.canvas.draw_idle()
            if self._changes_membership(cmd):
                self.reload_tree()
                self.select(None)
            self.refresh_inspector()
            self.sync_view_action()
            self.status(_t("실행 취소: {what}", what=cmd.describe()))

    def redo(self):
        cmd = self.session.history.redo()
        if cmd:
            self.canvas.draw_idle()
            if self._changes_membership(cmd):
                self.reload_tree()
                self.select(None)
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
        self.mark_dirty(False)
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

    def mark_dirty(self, dirty: bool = True):
        """고칠 것이 남았음을 그 문서의 탭에 표시한다.

        창 제목에만 붙이면 탭이 여럿일 때 어느 문서가 저장이 안 됐는지
        알 수 없다.
        """
        doc = self.doc
        if doc is None:
            return
        doc.dirty = dirty
        i = self.docs.indexOf(doc)
        self.docs.setTabText(i, doc.name + (" *" if dirty else ""))
        self.setWindowTitle(f"figtune — {doc.name}" + (" *" if dirty else ""))

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
        picked = self.selection()
        self.select_paths(picked) if picked else self.inspector.show([], {}, set())

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
