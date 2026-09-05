"""figtune 메인 윈도우."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.backends.backend_qtagg import (                   # noqa: E402
    NavigationToolbar2QT as NavToolbar)
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAction, QKeySequence  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog,  # noqa: E402
                               QHBoxLayout, QInputDialog, QLabel, QMainWindow,
                               QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea,
                               QSplitter, QStatusBar, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ...core import selector as sel  # noqa: E402
from ...core.session import Session  # noqa: E402
from .inspector import Inspector  # noqa: E402


BASE_DPI = 100.0


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
    """히트테스트와 텍스트 드래그를 담당."""

    def __init__(self, window: "MainWindow"):
        super().__init__(window.session.fig)
        self.win = window
        self._drag = None
        self.setFocusPolicy(Qt.StrongFocus)
        self.mpl_connect("button_press_event", self._press)
        self.mpl_connect("motion_notify_event", self._motion)
        self.mpl_connect("button_release_event", self._release)

    def _press(self, event):
        if event.inaxes is None or event.button != 1:
            return
        hits = self.win.session.pick(event)
        if not hits:
            self.win.select(None)
            return

        # 겹친 경우 사용자에게 고르게 한다 (zorder 역순)
        path = hits[0]
        if len(hits) > 1:
            menu = QMenu(self)
            acts = {menu.addAction(h): h for h in hits}
            chosen = menu.exec(self.mapToGlobal(
                self.mapFromParent(self.cursor().pos() - self.parentWidget().pos())))
            if chosen is None:
                return
            path = acts[chosen]

        self.win.select(path)
        if sel.parse(path).kind == "usertext" and event.xdata is not None:
            self._drag = (path, event.xdata, event.ydata)

    def _motion(self, event):
        if self._drag is None or event.inaxes is None or event.xdata is None:
            return
        path, _, _ = self._drag
        tid = sel.parse(path).name
        t = self.win.session.spec.text_by_id(tid)
        if t is None:
            return
        if t.coords == "data":
            x, y = event.xdata, event.ydata
        else:
            inv = event.inaxes.transAxes.inverted()
            x, y = inv.transform((event.x, event.y))
        self.win.session.move_text(tid, x, y)
        self.draw_idle()
        self.win.status(f"{tid} → ({x:.3f}, {y:.3f})")

    def _release(self, event):
        if self._drag is not None:
            self._drag = None
            self.win.refresh_inspector()
            self.win.mark_dirty()


class MainWindow(QMainWindow):
    def __init__(self, script: str | Path, python: str | None = None,
                 spec_in=None, spec_out=None, png_out=None, dpi: int = 300):
        super().__init__()
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
        self.tree.setHeaderLabels(["요소"])
        self.tree.itemSelectionChanged.connect(self._tree_selected)

        self.inspector = Inspector()
        self.inspector.edited.connect(self._on_edit)
        self.inspector.reset.connect(self._on_reset)

        self.code = QPlainTextEdit()
        self.code.setReadOnly(True)
        self.code.setStyleSheet("font-family: monospace; font-size: 11px;")

        right = QTabWidget()
        right.addTab(self.inspector, "속성")
        right.addTab(self.code, "코드")
        right.currentChanged.connect(
            lambda i: self._refresh_code() if i == 1 else None)
        self.right = right

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.tree)
        btn = QPushButton("패널 라벨 (a)(b)(c) 일괄 삽입")
        btn.clicked.connect(self._add_panel_labels)
        lv.addWidget(btn)
        btn2 = QPushButton("선택한 축에 텍스트 추가")
        btn2.clicked.connect(self._add_text)
        lv.addWidget(btn2)

        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        self.canvas_frame = CanvasFrame(self.canvas)
        cv.addWidget(NavToolbar(self.canvas, self))
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
        self._report_issues(report)

    # --- 메뉴 ------------------------------------------------------------

    def _build_menu(self):
        m = self.menuBar().addMenu("파일")
        self._act(m, "저장", "Ctrl+S", self.save)
        self._act(m, "스크립트 재실행", "Ctrl+R", self.reload_script)
        m.addSeparator()
        self._act(m, "내보내기…", "Ctrl+E", self.export)

        e = self.menuBar().addMenu("편집")
        self._act(e, "실행 취소", QKeySequence.Undo, self.undo)
        self._act(e, "다시 실행", QKeySequence.Redo, self.redo)

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
        if path is None:
            self.inspector.show_path(None, {}, set())
            return
        vals = self.session.values(path)
        over = {n for n in self.session.spec.of(path)}
        if sel.parse(path).kind == "usertext":
            over = set(vals)
        self.inspector.show_path(path, vals, over)
        self.status(path)
        if not from_tree:
            self._sync_tree_selection(path)

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
            self.status(f"적용 실패: {exc}")
            return
        if path == "fig" and name == "size_inches":
            self.canvas_frame.fit()
        self.canvas.draw_idle()
        self.mark_dirty()
        if self.right.currentIndex() == 1:
            self._refresh_code()

    def _on_reset(self, path, name):
        self.session.reset_prop(path, name)
        self.status(f"{path}.{name} override 제거됨 — 재실행하면 원래값으로 돌아갑니다")
        self.mark_dirty()

    def refresh_inspector(self):
        if getattr(self, "_current", None):
            self.inspector.refresh_values(self.session.values(self._current))

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
        text, ok = QInputDialog.getText(self, "텍스트 추가", "내용:")
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
            self.status(f"실행 취소: {cmd.describe()}")

    def redo(self):
        cmd = self.session.history.redo()
        if cmd:
            self.canvas.draw_idle()
            self.refresh_inspector()
            self.status(f"다시 실행: {cmd.describe()}")

    def save(self):
        hook = False
        if self.session.script and self.session.style_path:
            src = self.session.script.read_text(encoding="utf-8")
            if "apply_style" not in src:
                ans = QMessageBox.question(
                    self, "원본 스크립트 수정",
                    f"{self.session.script.name}에 import/호출 2줄을 추가할까요?\n"
                    "figtune이 원본 파일을 만지는 유일한 지점입니다.\n"
                    "거절해도 스타일 파일은 저장됩니다.")
                hook = ans == QMessageBox.Yes
        out = self.session.save(install_hook=hook)
        # 호출자(PowerPoint 애드인 등)가 지정한 경로에도 결과를 남긴다
        if self.spec_out:
            self.session.spec.dump(self.spec_out)
        if self.png_out:
            self.session.export(self.png_out, dpi=self.export_dpi)
        self.status(f"저장됨 — {Path(out['style']).name}, {Path(out['spec']).name}")
        self.setWindowTitle(self.windowTitle().rstrip(" *"))
        self._refresh_code()

    def reload_script(self):
        rep = self.session.reload()
        self.canvas.figure = self.session.fig
        self.canvas.draw_idle()
        self.reload_tree()
        self._report_issues(rep)

    def export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "내보내기", "figure.pdf",
            "PDF (*.pdf);;PNG (*.png);;SVG (*.svg)")
        if not path:
            return
        dpi, ok = QInputDialog.getInt(self, "DPI", "해상도:", 300, 50, 1200, 50)
        if not ok:
            return
        self.session.export(path, dpi=dpi)
        self.status(f"내보냄: {path}")

    # --- 알림 ------------------------------------------------------------

    def _refresh_code(self):
        try:
            src = self.session.preview_code()
        except Exception as exc:
            self.code.setPlainText(f"# 코드 생성 실패: {exc}")
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
            names = ", ".join(Path(p).name for p in moved[:5])
            msgs.append(f"입력 데이터가 바뀌었습니다: {names}\n"
                        f"그림이 달라지는 것은 정상입니다.")
        if rep.stale:
            lines = "\n".join(
                f"  · {p}  → 재매칭 제안: {i['suggest'] or '없음'}"
                for p, i in sorted(rep.stale.items()))
            if moved:
                # 데이터가 바뀌었으면 지문 불일치는 예상된 결과다.
                # 같은 경고를 띄우면 진짜 위험한 경우를 무시하게 된다.
                msgs.append(f"아래 항목의 지문이 달라졌으나, 데이터 변경으로 "
                            f"설명됩니다:\n{lines}")
            else:
                msgs.append(f"원본 스크립트가 변경되었습니다. 아래 항목은 다른 "
                            f"대상을 가리키고 있을 수 있습니다:\n{lines}")
        if rep.style_readonly:
            msgs.append("스타일 모듈이 수동 편집되어 GUI로 되읽을 수 없습니다. "
                        "저장하면 덮어씁니다.\n  " + "\n  ".join(rep.style_issues[:6]))
        if rep.apply_failures:
            msgs.append("일부 override 적용 실패:\n  " + "\n  ".join(
                f"{p}.{n}: {w}" for p, n, w in rep.apply_failures[:6]))
        if msgs:
            QMessageBox.warning(self, "확인 필요", "\n\n".join(msgs))


def launch(script: str | Path, python: str | None = None, spec_in=None,
           spec_out=None, png_out=None, dpi: int = 300) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(script, python=python, spec_in=spec_in,
                     spec_out=spec_out, png_out=png_out, dpi=dpi)
    win.show()
    return app.exec()
