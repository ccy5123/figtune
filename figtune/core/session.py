"""Session — 프론트엔드가 유일하게 호출하는 파사드.

이 모듈은 PySide6를 import하지 않는다. 이 경계가 나중에 웹/PowerPoint
어댑터를 붙일 수 있게 하는 유일한 조건이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..i18n import t as _t
from . import apply as ap
from . import canon
from . import codegen
from . import introspect
from . import parse as parsemod
from . import props as P
from . import runner
from . import selector as sel
from . import typefaces
from .history import Command, History
from .spec import Spec, UserText


@dataclass
class LoadReport:
    stale: dict[str, dict] = field(default_factory=dict)
    # 데이터 파일이 바뀐 경우. 지문 불일치의 원인이 코드가 아니라 데이터임을
    # 뜻하므로, 같은 경고를 띄우면 안 된다.
    data_changed: dict = field(default_factory=dict)
    style_readonly: bool = False
    style_issues: list[str] = field(default_factory=list)
    apply_failures: list[tuple] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.stale or self.style_readonly or self.apply_failures)


class Session:
    _last_sources: list = []

    def __init__(self, python: str | None = None):
        # python을 지정하면 그 인터프리터에서 스크립트를 실행하고 Figure만
        # 받아온다. figtune이 사용자 분석 환경과 다른 곳에 설치된 경우 필요.
        self.python = python
        self.script: Path | None = None
        self.spec = Spec()
        self.fig = None
        self.tree: introspect.Node | None = None
        self.history = History(self._apply_raw,
                               after=lambda: canon.light(self.spec))
        self.dirty = False
        self.style_readonly = False
        # (path, prop) -> override를 처음 걸기 직전의 값.
        # 이것이 없으면 실행 취소가 spec에서만 지우고 화면은 그대로여서,
        # 되돌린 것처럼 보이지 않는다.
        self._pristine: dict[tuple[str, str], Any] = {}

    # --- 경로 규약 -------------------------------------------------------

    @property
    def spec_path(self) -> Path | None:
        return self.script.with_suffix(".figtune.yaml") if self.script else None

    @property
    def style_path(self) -> Path | None:
        if not self.script:
            return None
        return self.script.with_name(self.script.stem + "_style.py")

    # --- 열기 ------------------------------------------------------------

    def open(self, script_path: str | Path, spec: Spec | None = None) -> LoadReport:
        """스크립트를 열고 spec을 적용한다.

        spec을 명시하면 디스크의 .figtune.yaml과 스타일 모듈을 읽지 않는다.
        PowerPoint 도형처럼 spec이 다른 곳에 보관된 경우에 쓴다.
        """
        self.script = Path(script_path).resolve()
        rep = LoadReport()

        # 글꼴을 새로 깔아도 matplotlib은 자기 캐시를 갱신하지 않는다. 여기서
        # 잡지 않으면 '분명 깔았는데 목록에 없다'로 막힌다.
        typefaces.ensure_fresh()
        # 기본 글꼴은 스크립트가 돌기 전에 얹어야 한다. rcParams는 이미
        # 만들어진 artist에 소급되지 않는다.
        self._font_defaults = typefaces.default_rcparams()
        if self._font_defaults:
            import matplotlib as mpl
            mpl.rcParams.update(self._font_defaults)

        result = self._run()
        if not result.figures:
            raise RuntimeError(_t("스크립트가 figure를 만들지 않았습니다."))
        self.fig = result.figure

        self._last_sources = result.data_sources
        self._pristine.clear()

        if spec is not None:
            self.spec = spec
            self.spec.script = self.script.name
            rep.stale = (introspect.check_stale(self.fig, self.spec.fingerprints)
                         if self.spec.fingerprints else {})
            rep.apply_failures = ap.apply_spec(self.fig, self.spec).failed
            self.refresh_tree()
            self.history.clear()
            self.dirty = False
            return rep

        # 기존 spec 로드
        if self.spec_path and self.spec_path.exists():
            self.spec = Spec.load(self.spec_path)
        else:
            self.spec = Spec()

        # 손으로 고친 스타일 모듈이 있으면 그쪽을 우선한다
        if self.style_path and self.style_path.exists():
            pr = parsemod.parse_file(self.style_path)
            if pr.clean:
                merged = pr.spec
                # 스타일 모듈에는 담기지 않는 항목들을 옮겨온다.
                # 데이터 출처를 빠뜨리면 '이 그림이 어떤 데이터에서 나왔는지'가
                # 재실행 한 번에 사라진다.
                merged.fingerprints = self.spec.fingerprints
                merged.data_sources = self.spec.data_sources
                merged.script = self.spec.script
                self.spec = merged
            else:
                rep.style_readonly = True
                rep.style_issues = pr.unhandled

        self.style_readonly = rep.style_readonly
        self.spec.script = self.script.name
        self.spec.style_module = self.style_path.name if self.style_path else ""

        # 지문 대조 — 어긋나면 조용히 넘어가지 않는다
        if self.spec.fingerprints:
            rep.stale = introspect.check_stale(self.fig, self.spec.fingerprints)

        for key, value in getattr(self, "_font_defaults", {}).items():
            self.spec.rcparams.setdefault(key, value)

        report = ap.apply_spec(self.fig, self.spec)
        rep.apply_failures = report.failed
        rep.data_changed = self.data_changes()

        self.spec = canon.spec(self.spec)
        self.spec.fingerprints = introspect.fingerprints(self.fig)
        # data_sources는 여기서 덮어쓰지 않는다. 덮어쓰면 '이 그림이 만들어질
        # 당시의 데이터'라는 기록이 사라져 비교할 대상이 없어진다.
        # 갱신은 save() 시점에만 한다.
        self.refresh_tree()
        self.history.clear()
        self.dirty = False
        return rep

    def reload(self) -> LoadReport:
        """원본 스크립트가 바뀐 뒤 다시 실행한다. spec은 유지."""
        keep = self.spec
        rep = LoadReport()
        result = self._run()
        if not result.figures:
            raise RuntimeError(_t("스크립트가 figure를 만들지 않았습니다."))
        self.fig = result.figure
        self.spec = keep
        if self.spec.fingerprints:
            rep.stale = introspect.check_stale(self.fig, self.spec.fingerprints)
        rep.apply_failures = ap.apply_spec(self.fig, self.spec).failed
        self.refresh_tree()
        return rep

    def _run(self):
        if self.python:
            return runner.run_script_subprocess(self.script, python=self.python)
        return runner.run_script(self.script)

    def refresh_tree(self) -> None:
        self.tree = introspect.build(self.fig)

    # --- 조회 ------------------------------------------------------------

    def props_for(self, path: str) -> list:
        return P.props_for(sel.parse(path).kind)

    def values(self, path: str) -> dict:
        """인스펙터 표시값: override가 있으면 그 값, 없으면 figure 현재값."""
        cur = introspect.current_values(self.fig, path)
        s = sel.parse(path)
        if s.kind == "usertext":
            t = self.spec.text_by_id(s.name)
            if t is not None:
                cur.update({"text": t.text, "position": list(t.position)})
                cur.update(t.style())
            return cur
        cur.update(self.spec.of(path))
        return cur

    def is_overridden(self, path: str, name: str) -> bool:
        s = sel.parse(path)
        if s.kind == "usertext":
            return True          # user text는 전부 figtune 소유
        return name in self.spec.of(path)

    # --- 편집 ------------------------------------------------------------

    def set_prop(self, path: str, name: str, value: Any, record: bool = True) -> None:
        kind = sel.parse(path).kind
        # 값은 spec에 들어가기 전에 정규형으로 접힌다. 여기서 하지 않으면
        # '-'와 'solid'가 서로 다른 override로 남는다.
        value = canon.value(kind, name, value)
        old = self.spec.of(path).get(name, None)
        self._apply_raw(path, name, value)
        canon.light(self.spec)          # 편집 결과도 정규형을 유지한다
        if record:
            self.history.push(Command(path, name, old, value))
        self.dirty = True

    def reset_prop(self, path: str, name: str) -> None:
        """override를 제거하고 화면도 원래 값으로 되돌린다."""
        old = self.spec.of(path).get(name)
        self._apply_raw(path, name, None)
        canon.light(self.spec)
        self.history.push(Command(path, name, old, None))
        self.dirty = True

    def _restore_pristine(self, path: str, name: str) -> None:
        """override를 걸기 전의 값으로 figure를 되돌린다.

        spec에서 지우는 것만으로는 부족하다. 살아있는 artist는 이미 바뀐
        상태이고, 스크립트를 다시 돌리기 전까지는 스스로 돌아오지 않는다.
        그래서 처음 덮어쓰기 직전의 값을 기억해 두었다가 여기서 되돌린다.
        """
        old = self._pristine.pop((path, name), None)
        if old is None or self.fig is None:
            return
        s = sel.parse(path)
        try:
            if s.kind == "legend":
                # 범례는 한 번에 다시 만들어야 한다. 하나만 되돌리면
                # 나머지 override가 기본값으로 같이 날아간다.
                P.apply_legend(self.fig.axes[s.axes],
                               {**self.spec.of(path), name: old})
            else:
                P.apply(self.fig, path, name, old)
        except Exception:
            pass                # 되돌리지 못해도 spec은 이미 정리됐다

    def _apply_raw(self, path: str, name: str, value: Any) -> None:
        if not path:
            return
        s = sel.parse(path)
        if value is not None:
            value = canon.value(s.kind, name, value)

        # user text의 속성은 overrides가 아니라 UserText 객체에 산다.
        # 그래야 codegen이 ax.text(...) 호출 하나로 묶어 내보낼 수 있고,
        # 파싱도 그 한 줄만 읽으면 된다.
        if s.kind == "usertext":
            t = self.spec.text_by_id(s.name)
            if t is None:
                return
            if name == "position" and value is not None:
                t.position = [float(value[0]), float(value[1])]
            elif hasattr(t, name):
                setattr(t, name, value)
            ap.sync_text(self.fig, self.spec, s.name)
            return

        if value is None:
            self.spec.unset(path, name)
            self._restore_pristine(path, name)
            return

        key = (path, name)
        if key not in self._pristine:
            self._pristine[key] = P.get(self.fig, path, name)
        ap.apply_one(self.fig, self.spec, path, name, value)

    # --- user text -------------------------------------------------------

    # 기본값은 번역하지 않는다. spec과 생성 코드에 그대로 실려 그림에 찍히므로,
    # 언어에 따라 달라지면 같은 spec이 사람마다 다른 그림을 낸다.
    def add_text(self, axes_index: int, text: str = "text",
                 position=(0.5, 0.5), coords: str = "axes") -> str:
        tid = self.spec.new_text_id()
        self.spec.texts.append(UserText(id=tid, axes=axes_index, text=text,
                                        position=[float(position[0]), float(position[1])],
                                        coords=coords))
        ap.sync_text(self.fig, self.spec, tid)
        self.refresh_tree()
        self.dirty = True
        return tid

    def move_text(self, tid: str, x: float, y: float) -> None:
        t = self.spec.text_by_id(tid)
        if t is None:
            return
        t.position = [float(x), float(y)]
        ap.sync_text(self.fig, self.spec, tid)
        self.dirty = True

    def can_delete(self, path: str) -> bool:
        """원본 스크립트가 만든 텍스트는 지우지 않는다.

        지우면 다음 재실행에 되살아나서 사용자가 혼란스러워진다. 감추려면
        visible=False override를 쓰면 되고, 그건 코드로도 남는다.
        """
        return sel.parse(path).kind == "usertext"

    def delete_text(self, tid: str) -> None:
        ap.remove_text(self.fig, self.spec, tid)
        self.refresh_tree()
        self.dirty = True

    def add_panel_labels(self, template: str = "({a})", **style) -> list[str]:
        """모든 axes에 (a)(b)(c) 라벨을 일괄 삽입한다."""
        ids = []
        for i in range(len(self.fig.axes)):
            label = template.format(a=chr(ord("a") + i), A=chr(ord("A") + i), n=i + 1)
            tid = self.add_text(i, label, position=(-0.15, 1.02), coords="axes")
            path = sel.usertext(i, tid)
            self.set_prop(path, "fontweight", style.get("fontweight", "bold"))
            self.set_prop(path, "fontsize", style.get("fontsize", 11))
            ids.append(tid)
        return ids

    # --- 히트테스트 ------------------------------------------------------

    def pick(self, event) -> list[str]:
        """캔버스 클릭 → 후보 selector 목록 (앞쪽이 위에 있는 것).

        겹친 artist에서 애매하므로 단일 값이 아니라 목록을 반환한다.
        GUI는 2개 이상이면 사용자에게 고르게 한다.
        """
        if self.tree is None or event.inaxes is None:
            return []
        try:
            ax_i = self.fig.axes.index(event.inaxes)
        except ValueError:
            return []

        hits: list[tuple[float, str]] = []
        for node in self.tree.walk():
            if not node.pickable:
                continue
            s = sel.parse(node.path)
            if s.axes != ax_i:
                continue
            try:
                artist = sel.resolve(self.fig, node.path)
                contains, _ = artist.contains(event)
            except Exception:
                continue
            if contains:
                z = getattr(artist, "get_zorder", lambda: 0)()
                hits.append((z, node.path))

        hits.sort(key=lambda t: -t[0])
        return [p for _, p in hits]

    def data_changes(self) -> dict:
        """spec에 기록된 데이터 출처와 이번 실행의 출처를 비교한다.

        figtune은 데이터를 들고 있지 않다. 대신 지문을 남겨 '이 그림이 어떤
        데이터에서 나왔는지'를 나중에 따질 수 있게 한다.
        """
        from . import provenance
        return provenance.compare(self.spec.data_sources, self._last_sources)

    # --- 저장 / 내보내기 -------------------------------------------------

    def save(self, install_hook: bool = False) -> dict:
        if not self.script:
            raise RuntimeError(_t("열린 스크립트가 없습니다."))
        self.spec.fingerprints = introspect.fingerprints(self.fig)
        self.spec.data_sources = [d.to_dict() for d in self._last_sources]
        self.spec = canon.spec(self.spec)
        self.spec.dump(self.spec_path)
        codegen.write(self.spec, self.style_path, specfile=self.spec_path.name)
        hooked = False
        if install_hook:
            hooked = codegen.install_hook(self.script, self.style_path.stem)
        self.dirty = False
        return {"spec": str(self.spec_path), "style": str(self.style_path),
                "hook_installed": hooked}

    def normalize(self) -> None:
        """상태를 정규형으로 되돌린다. 이미 정규형이면 아무 일도 없다."""
        self.spec = canon.spec(self.spec)

    def preview_code(self) -> str:
        return codegen.generate(self.spec,
                                specfile=self.spec_path.name if self.spec_path else "",
                                stem=self.style_path.stem if self.style_path else "style")

    def export(self, path: str | Path, dpi: int | None = None,
               transparent: bool = False, bbox_inches: str | None = "tight") -> Path:
        out = Path(path)
        from matplotlib.figure import Figure
        dpi = dpi or self.spec.get("fig", "dpi") or 300
        Figure.savefig(self.fig, out, dpi=dpi,
                       transparent=transparent, bbox_inches=bbox_inches)
        return out
