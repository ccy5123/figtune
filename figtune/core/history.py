"""undo/redo 커맨드 스택.

커맨드는 (path, prop, old, new)만 담는다. figure 스냅샷을 뜨지 않으므로
가볍고, spec이 단일 원본이라는 성질 덕분에 이것만으로 충분하다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

MAX_DEPTH = 100


@dataclass
class Command:
    path: str
    prop: str
    old: Any
    new: Any
    label: str = ""

    def describe(self) -> str:
        return self.label or f"{self.path}.{self.prop}"


class History:
    def __init__(self, apply_fn: Callable[[str, str, Any], None],
                 depth: int = MAX_DEPTH, after: Callable[[], None] | None = None):
        self._apply = apply_fn
        # 되돌린 뒤에도 정규형이 유지되도록 호출자가 훅을 건다
        self.after = after
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._sealed = False
        self.depth = depth

    def push(self, cmd: Command) -> None:
        # 같은 속성을 연속으로 만지면 (슬라이더 드래그) 하나로 합친다
        if self._undo and not self._sealed:
            last = self._undo[-1]
            if last.path == cmd.path and last.prop == cmd.prop:
                last.new = cmd.new
                self._redo.clear()
                return
        self._sealed = False
        self._undo.append(cmd)
        if len(self._undo) > self.depth:
            self._undo.pop(0)
        self._redo.clear()

    def seal(self) -> None:
        """다음 push를 직전 커맨드와 합치지 않는다.

        끌기 하나가 실행 취소 한 칸이어야 한다. 경계를 긋지 않으면 같은
        속성을 두 번 만졌을 때 둘이 한 칸으로 합쳐져, 실행 취소 한 번이
        두 번의 조작을 되돌린다.

        표식을 스택에 넣는 대신 깃발을 세운다. 표식을 넣으면 undo가 그것을
        만나 아무것도 하지 않는 헛걸음을 하게 된다.
        """
        self._sealed = True

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> Command | None:
        if not self._undo:
            return None
        cmd = self._undo.pop()
        self._apply(cmd.path, cmd.prop, cmd.old)
        self._redo.append(cmd)
        if self.after is not None:
            self.after()
        return cmd

    def redo(self) -> Command | None:
        if not self._redo:
            return None
        cmd = self._redo.pop()
        self._apply(cmd.path, cmd.prop, cmd.new)
        self._undo.append(cmd)
        if self.after is not None:
            self.after()
        return cmd

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def __len__(self) -> int:
        return len(self._undo)
