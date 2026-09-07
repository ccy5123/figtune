"""조립 화면 — 격자에 열려 있는 그림들을 놓고 하나로 만든다.

칸을 끌어 묶고, 묶인 칸을 나누고, 빈 칸의 +를 눌러 탭을 고른다. 규칙은
core.gridlayout이 갖고 있고 여기서는 그리기와 조작만 한다.

만들기를 누르면 병합 스크립트를 쓰고 그것을 새 탭으로 연다.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                               QHBoxLayout, QLabel, QMenu, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

from ...core.gridlayout import GridLayout, LayoutError
from ...i18n import t as _t


class CellGrid(QWidget):
    """격자를 그리고 칸을 고르게 한다."""

    assign_requested = Signal(int)      # 빈 칸의 +를 눌렀다
    selection_changed = Signal()

    MIN_CELL = 90
    GAP = 6
    MARGIN = 10

    def __init__(self, layout: GridLayout, parent=None):
        super().__init__(parent)
        self.layout_model = layout
        self._region: tuple | None = None    # 끌어서 고른 (r0, c0, r1, c1)
        self._anchor: tuple | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(
            self.MARGIN * 2 + layout.cols * (self.MIN_CELL + self.GAP),
            self.MARGIN * 2 + layout.rows * (self.MIN_CELL + self.GAP))

    # --- 기하 -------------------------------------------------------------

    def _cell_size(self) -> tuple[float, float]:
        g = self.layout_model
        w = (self.width() - self.MARGIN * 2 - self.GAP * (g.cols - 1)) / g.cols
        h = (self.height() - self.MARGIN * 2 - self.GAP * (g.rows - 1)) / g.rows
        return max(1.0, w), max(1.0, h)

    def cell_at(self, x: float, y: float) -> tuple[int, int] | None:
        g = self.layout_model
        cw, ch = self._cell_size()
        col = int((x - self.MARGIN) // (cw + self.GAP))
        row = int((y - self.MARGIN) // (ch + self.GAP))
        if 0 <= row < g.rows and 0 <= col < g.cols:
            return row, col
        return None

    def rect_of(self, slot) -> QRect:
        cw, ch = self._cell_size()
        x = self.MARGIN + slot.col * (cw + self.GAP)
        y = self.MARGIN + slot.row * (ch + self.GAP)
        w = slot.colspan * cw + (slot.colspan - 1) * self.GAP
        h = slot.rowspan * ch + (slot.rowspan - 1) * self.GAP
        return QRect(int(x), int(y), int(w), int(h))

    # --- 고르기 -----------------------------------------------------------

    def region(self) -> tuple | None:
        """끌어서 고른 범위 (row, col, rowspan, colspan). 없으면 None."""
        if self._region is None:
            return None
        r0, c0, r1, c1 = self._region
        return (min(r0, r1), min(c0, c1),
                abs(r1 - r0) + 1, abs(c1 - c0) + 1)

    def clear_region(self) -> None:
        self._region = None
        self.selection_changed.emit()
        self.update()

    def mousePressEvent(self, event):
        cell = self.cell_at(event.position().x(), event.position().y())
        if cell is None:
            return
        self._anchor = cell
        self._region = (*cell, *cell)
        self.selection_changed.emit()
        self.update()

    def mouseMoveEvent(self, event):
        if self._anchor is None:
            return
        cell = self.cell_at(event.position().x(), event.position().y())
        if cell is not None:
            self._region = (*self._anchor, *cell)
            self.selection_changed.emit()
            self.update()

    def mouseReleaseEvent(self, event):
        cell = self.cell_at(event.position().x(), event.position().y())
        was_click = self._anchor is not None and cell == self._anchor
        self._anchor = None
        if not was_click or cell is None:
            return
        # 움직이지 않고 뗐다 — 그 칸을 채우려는 것이다
        slot = self.layout_model.slot_at(*cell)
        if not slot.ref:
            self.assign_requested.emit(self.layout_model.index_at(*cell))

    # --- 그리기 -----------------------------------------------------------

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        picked = self.region()
        for slot in self.layout_model.slots:
            rect = self.rect_of(slot)
            inside = picked is not None and slot.inside(*picked)
            painter.setPen(QPen(QColor("#2c7be5" if inside else "#bbbbbb"),
                                2 if inside else 1))
            painter.setBrush(QColor("#eaf3fd") if inside else QColor("#fbfbfb"))
            painter.drawRoundedRect(rect, 4, 4)

            painter.setPen(QColor("#333333" if slot.ref else "#9a9a9a"))
            text = Path(slot.ref).name if slot.ref else "+"
            if not slot.ref:
                f = painter.font()
                f.setPointSize(max(12, f.pointSize() + 6))
                painter.setFont(f)
            painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, text)
            if not slot.ref:
                f = painter.font()
                f.setPointSize(max(1, f.pointSize() - 6))
                painter.setFont(f)
        painter.end()


class MontageDialog(QDialog):
    """격자에 탭들을 놓고 병합 스크립트를 만든다."""

    def __init__(self, window, rows: int, cols: int):
        super().__init__(window)
        self.win = window
        self.model = GridLayout(rows, cols)
        self.setWindowTitle(_t("그림 합치기"))
        self.resize(720, 520)

        self.grid = CellGrid(self.model, self)
        self.grid.assign_requested.connect(self._choose_for)
        self.grid.selection_changed.connect(self._sync_buttons)

        self.btn_merge = QPushButton(_t("칸 묶기"))
        self.btn_merge.clicked.connect(self._merge)
        self.btn_split = QPushButton(_t("칸 나누기"))
        self.btn_split.clicked.connect(self._split)
        self.btn_clear = QPushButton(_t("칸 비우기"))
        self.btn_clear.clicked.connect(self._clear)

        row = QHBoxLayout()
        for b in (self.btn_merge, self.btn_split, self.btn_clear):
            row.addWidget(b)
        row.addStretch(1)

        self.hint = QLabel()
        self.hint.setStyleSheet("color:#666;")

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        self.buttons.button(QDialogButtonBox.Save).setText(
            _t("저장하고 종료"))
        self.buttons.accepted.connect(self._build)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            _t("빈 칸을 눌러 열려 있는 탭을 놓으세요. "
               "여러 칸을 끌어 고르면 묶을 수 있습니다.")))
        lay.addWidget(self.grid, 1)
        lay.addLayout(row)
        lay.addWidget(self.hint)
        lay.addWidget(self.buttons)

        self.result_path: Path | None = None
        self._sync_buttons()

    # --- 상태 -------------------------------------------------------------

    def _sync_buttons(self):
        region = self.grid.region()
        many = region is not None and (region[2] > 1 or region[3] > 1)
        self.btn_merge.setEnabled(many)

        one = None
        if region is not None:
            one = self.model.slot_at(region[0], region[1])
        self.btn_split.setEnabled(
            one is not None and (one.rowspan > 1 or one.colspan > 1))
        self.btn_clear.setEnabled(one is not None and bool(one.ref))

        empty = len(self.model.empty_slots())
        self.hint.setText("" if not empty
                          else _t("빈 칸 {n}개", n=empty))
        self.buttons.button(QDialogButtonBox.Save).setEnabled(empty == 0)

    def _warn(self, exc):
        QMessageBox.warning(self, _t("그림 합치기"), str(exc))

    # --- 조작 -------------------------------------------------------------

    def _merge(self):
        region = self.grid.region()
        if region is None:
            return
        try:
            self.model.merge(*region)
        except LayoutError as exc:
            self._warn(exc)
            return
        self.grid.clear_region()
        self.grid.update()
        self._sync_buttons()

    def _split(self):
        region = self.grid.region()
        if region is None:
            return
        self.model.split(self.model.index_at(region[0], region[1]))
        self.grid.clear_region()
        self.grid.update()
        self._sync_buttons()

    def _clear(self):
        region = self.grid.region()
        if region is None:
            return
        self.model.clear(self.model.index_at(region[0], region[1]))
        self.grid.update()
        self._sync_buttons()

    def candidates(self) -> list[tuple[str, str, str | None]]:
        """놓을 수 있는 것들: (보일 이름, 경로, 안 되는 이유 또는 None).

        합칠 수 없다는 것을 칸을 다 채우고 나서 알면 늦다. 목록에서 바로
        보이고, 왜 안 되는지도 함께 나온다.
        """
        from ...core.montage_build import panel_cells, panel_problem

        out = []
        for doc in self.win.documents():
            if doc.session.script is None:
                continue
            path = str(doc.session.script)
            problem = panel_problem(path)
            if problem is None:
                # 이미 여러 패널짜리면 그만큼의 자리가 필요하다. 놓기 전에
                # 알아야 좁은 칸에 밀어 넣고 나서 눈치채는 일이 없다.
                r, c = panel_cells(path)
                name = doc.name if (r, c) == (1, 1) else \
                    _t("{name} — {r}x{c} 칸 권장", name=doc.name, r=r, c=c)
            else:
                name = doc.name
            out.append((name, path, problem))
        return out

    def _choose_for(self, index: int):
        """빈 칸에 놓을 것을 고른다 — 열려 있는 탭들 중에서."""
        menu = QMenu(self)
        acts = {}
        cands = self.candidates()
        for name, path, problem in cands:
            act = menu.addAction(name if not problem
                                 else f"{name} — {problem}")
            if problem:
                # 고를 수 없게 두되 이유를 남긴다. 목록에서 빼 버리면
                # '내 파일이 왜 없지'가 된다.
                act.setEnabled(False)
                act.setToolTip(problem)
            else:
                acts[act] = path
        if not cands:
            menu.addAction(_t("열려 있는 탭이 없습니다")).setEnabled(False)
        menu.addSeparator()
        browse = menu.addAction(_t("파일에서…"))

        chosen = menu.exec(self.cursor().pos())
        if chosen is None:
            return
        if chosen is browse:
            path, _ = QFileDialog.getOpenFileName(
                self, _t("스크립트 열기"), "", "Python (*.py)")
            if not path:
                return
        else:
            path = acts.get(chosen)
            if path is None:
                return
        self.place(index, path)

    def place(self, index: int, path: str) -> bool:
        """칸에 그림을 놓는다. 놓을 수 없으면 이유를 알리고 놓지 않는다."""
        from ...core.montage_build import panel_problem

        problem = panel_problem(path)
        if problem:
            QMessageBox.warning(
                self, _t("그림 합치기"),
                _t("{name}은(는) 합칠 수 없습니다 — {why}\n\n"
                   "각 스크립트에 다음 형태를 추가하세요:\n"
                   "    def plot(ax):\n        ...\n"
                   "    if __name__ == '__main__':\n"
                   "        fig, ax = plt.subplots(); plot(ax)\n"
                   "단독 실행도 그대로 되고 합치기도 가능해집니다.",
                   name=Path(path).name, why=problem))
            return False
        try:
            self.model.assign(index, path)
        except LayoutError as exc:
            self._warn(exc)
            return False
        self.grid.update()
        self._sync_buttons()
        return True

    # --- 만들기 -----------------------------------------------------------

    def _build(self):
        from ...core.montage_build import (MontageSpec, data_warnings,
                                           generate_subplot_script)

        try:
            panels = self.model.to_panels()
        except LayoutError as exc:
            self._warn(exc)
            return

        start = str(Path(panels[0].script).with_name("merged.py"))
        out, _ = QFileDialog.getSaveFileName(
            self, _t("병합 스크립트 저장"), start, "Python (*.py)")
        if not out:
            return

        ms = MontageSpec(rows=self.model.rows, cols=self.model.cols,
                         panels=panels)

        # 데이터를 상대 경로로 읽는 패널은 병합 파일이 옮겨지면 찾지 못한다.
        # 실행할 때가 되어서야 알면 늦다 — 그때 나오는 것은 날것의
        # FileNotFoundError뿐이라 왜 그런지도 알 수 없다.
        warns = data_warnings(ms, Path(out).parent,
                              base_dir=Path(panels[0].script).parent)
        if warns and QMessageBox.question(
                self, _t("그림 합치기"),
                "\n\n".join(warns) + "\n\n" + _t("그래도 만들까요?"),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        try:
            self.result_path = generate_subplot_script(
                ms, out, base_dir=Path(out).parent)
        except Exception as exc:
            self._warn(exc)
            return
        self.accept()
