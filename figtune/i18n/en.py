"""English catalog.

Keys are the Korean source strings verbatim. A missing key falls back to the
source string, so a gap shows up as Korean text rather than a crash — and
tests/test_i18n.py fails the build when a key is missing.

Named placeholders ({path}, {n}, ...) must survive translation. The same test
checks that too: a translation may reorder them but may not drop or invent one.
"""

MESSAGES = {

    # --- 프로퍼티 라벨 (인스펙터) ---------------------------------------
    # 인스펙터 폼은 좁다. 라벨은 matplotlib 용어를 쓰되 짧게 유지한다.
    "크기 (in)": "Size (in)",
    "DPI": "DPI",
    "축 상자": "Plot box",
    "배경색": "Background",
    "x 범위": "x range",
    "y 범위": "y range",
    "x 스케일": "x scale",
    "y 스케일": "y scale",
    "제목 여백": "Title pad",
    "x라벨 여백": "x label pad",
    "y라벨 여백": "y label pad",
    "고도각": "Elevation",
    "방위각": "Azimuth",
    "롤": "Roll",
    "확대": "Zoom",
    "내용": "Text",
    "크기": "Size",
    "색": "Color",
    "글꼴": "Font",
    "굵기": "Weight",
    "기울임": "Italic",
    "회전": "Rotation",
    "가로 정렬": "H align",
    "세로 정렬": "V align",
    "표시": "Visible",
    # 범례 loc(이름 있는 배치)과 텍스트 position(축 좌표)은 다른 것이다.
    # 한때 둘 다 "위치"였고 영어로는 구분이 사라졌다.
    "위치": "Position",
    "좌표": "Coordinates",
    "앵커": "Anchor",
    "테두리": "Frame",
    "글자 크기": "Font size",
    "범례 제목": "Legend title",
    "제목 크기": "Title size",
    "z순서": "z-order",
    "선 색": "Line color",
    "선 두께": "Line width",
    "선 종류": "Line style",
    "마커": "Marker",
    "마커 크기": "Marker size",
    "마커 내부색": "Marker fill",
    "마커 테두리색": "Marker edge color",
    "마커 테두리": "Marker edge width",
    "투명도": "Alpha",
    "범례 라벨": "Legend label",
    "채움색": "Fill color",
    "테두리색": "Edge color",
    "테두리 두께": "Edge width",
    "두께": "Width",
    "바깥 오프셋": "Outward offset",
    "라벨 크기": "Label size",
    "방향": "Direction",
    "길이": "Length",
    "여백": "Pad",
    "눈금색": "Tick color",
    "라벨색": "Label color",
    "라벨 회전": "Label rotation",
    "아래 표시": "Show bottom",
    "위 표시": "Show top",
    "왼쪽 표시": "Show left",
    "오른쪽 표시": "Show right",
    "눈금 간격": "Tick spacing",
    "대상": "Which",
    "열 수": "Columns",
    "항목 간격": "Item spacing",
    "라벨": "Labels",

    # --- 글꼴 추천 설명 ---------------------------------------------------
    "한중일을 모두 덮는 표준 본문용":
        "Standard body text covering Chinese, Japanese and Korean",
    "한국어 UI·본문에 자연스러운 고딕":
        "A gothic that reads naturally for Korean UI and body text",
    "국문 논문 본문에 쓰는 명조":
        "The serif used for body text in Korean papers",
    "Arial 대체. 지표 폭이 같아 배치가 안 바뀐다":
        "An Arial replacement. Metric-compatible, so layout does not shift",
    "LaTeX 본문 글꼴. 논문과 그림을 맞출 때":
        "The LaTeX body font, for matching a figure to its paper",
    "matplotlib 기본. 늘 있다": "The matplotlib default. Always present",

    # --- 트리 라벨 -------------------------------------------------------
    "(비어 있음)": "(empty)",
    "(라벨 없음)": "(no label)",
    "(범례 전용)": "(legend only)",
    "요소": "Element",

    # --- 메뉴 / 탭 / 버튼 ------------------------------------------------
    "파일": "File",
    "열기…": "Open…",
    "합칠 격자를 고르세요": "Choose a grid to merge into",

    # --- 그림 합치기 ------------------------------------------------------
    "그림 합치기": "Merge figures",
    "그래도 만들까요?": "Build it anyway?",
    "{script}는 경로를 변수로 만듭니다 ({calls}). 그것이 상대 경로라면 "
    "병합 파일을 {out}에 두었을 때 찾지 못합니다 — 절대 경로로 바꾸거나 "
    "데이터 옆에 저장하세요.":
        "{script} builds its path from a variable ({calls}). If that is a "
        "relative path, the merge file will not find it in {out} — make the "
        "path absolute, or save next to the data.",
    "{name} — {r}x{c} 칸 권장": "{name} — best in {r}x{c} cells",
    "ax를 받는 plot(ax) 함수가 없습니다": "no plot(ax) function taking ax",
    "읽지 못했습니다: {err}": "could not read it: {err}",
    "{name}은(는) 합칠 수 없습니다 — {why}\n\n"
    "각 스크립트에 다음 형태를 추가하세요:\n"
    "    def plot(ax):\n        ...\n"
    "    if __name__ == '__main__':\n"
    "        fig, ax = plt.subplots(); plot(ax)\n"
    "단독 실행도 그대로 되고 합치기도 가능해집니다.":
        "{name} cannot be merged — {why}\n\n"
        "Add this shape to the script:\n"
        "    def plot(ax):\n        ...\n"
        "    if __name__ == '__main__':\n"
        "        fig, ax = plt.subplots(); plot(ax)\n"
        "Running it on its own still works, and merging becomes possible.",
    "그림 합치기…": "Merge figures…",
    "빈 칸을 눌러 열려 있는 탭을 놓으세요. "
    "여러 칸을 끌어 고르면 묶을 수 있습니다.":
        "Click an empty cell to place an open tab. Drag across cells to "
        "merge them.",
    "칸 묶기": "Merge cells",
    "칸 나누기": "Split cell",
    "칸 비우기": "Empty cell",
    "저장하고 종료": "Save and close",
    "빈 칸 {n}개": "{n} empty cells",
    "열려 있는 탭이 없습니다": "no open tabs",
    "파일에서…": "From a file…",
    "병합 스크립트 저장": "Save merge script",
    "({r},{c})는 격자를 벗어납니다.": "({r},{c}) is outside the grid.",
    "{ref}는 이미 다른 칸에 있습니다.": "{ref} is already in another cell.",
    "묶을 범위가 격자를 벗어납니다: ({r},{c}) {rs}x{cs}":
        "the region to merge falls outside the grid: ({r},{c}) {rs}x{cs}",
    "이미 묶인 칸에 걸쳐 있습니다. 그 칸을 먼저 나누세요.":
        "This straddles an already merged cell. Split that cell first.",
    "채워진 칸이 {n}개입니다. 하나만 남기고 비운 뒤 묶으세요.":
        "{n} of these cells are filled. Leave one and empty the rest first.",
    "빈 칸이 {n}개 남았습니다. 모두 채운 뒤 만드세요.":
        "{n} cells are still empty. Fill them all first.",
    "스크립트 열기": "Open script",
    "탭 닫기": "Close tab",
    "열지 못했습니다: {err}": "could not open it: {err}",
    "저장": "Save",
    "스크립트 재실행": "Re-run script",
    "내보내기…": "Export…",
    "편집": "Edit",
    "실행 취소": "Undo",
    "다시 실행": "Redo",
    "삭제": "Delete",
    "{n}개 삭제됨": "{n} deleted",
    "언어": "Language",
    "시스템 따름": "Follow system",
    "속성": "Properties",
    "코드": "Code",
    "패널 라벨 (a)(b)(c) 일괄 삽입": "Insert (a)(b)(c) panel labels",
    "선택한 축에 텍스트 추가": "Add text to selected axes",

    # --- 대화상자 / 상태줄 -----------------------------------------------
    "캔버스나 트리에서 요소를 선택하세요.":
        "Select an element on the canvas or in the tree.",
    "이 속성의 override 제거": "Remove the override on this property",
    "{which}의 좌표를 지정해 두어 효과가 없습니다. "
    "좌표 override를 지우면 다시 살아납니다.":
        "No effect: {which} has explicit coordinates. Remove that override "
        "to bring this back.",
    "figtune이 지정한 값 (override)": "Value set by figtune (override)",
    "쉼표로 구분": "comma separated",
    "색 선택": "Pick a color",
    "텍스트 추가": "Add text",
    "내용:": "Text:",
    "내보내기": "Export",
    "해상도:": "Resolution:",
    "확인 필요": "Needs your attention",
    "없음": "none",
    "적용 실패: {err}": "Could not apply: {err}",
    "내보냄: {path}": "Exported: {path}",
    "{what}: {desc}": "{what}: {desc}",
    "저장됨 — {style}, {spec}": "Saved — {style}, {spec}",
    "# 코드 생성 실패: {err}": "# could not generate code: {err}",
    "{path}.{name} override 제거됨 — 재실행하면 원래값으로 돌아갑니다":
        "Override on {path}.{name} removed — re-running restores the "
        "original value",
    "원본 스크립트 수정": "Edit the original script",
    "{name}에 import/호출 2줄을 추가할까요?\n"
    "figtune이 원본 파일을 만지는 유일한 지점입니다.\n"
    "거절해도 스타일 파일은 저장됩니다.":
        "Add the two import/call lines to {name}?\n"
        "This is the only place where figtune touches your original file.\n"
        "Declining still saves the style file.",

    # --- 로드 리포트 -----------------------------------------------------
    "입력 데이터가 바뀌었습니다: {names}\n그림이 달라지는 것은 정상입니다.":
        "The input data changed: {names}\n"
        "It is expected that the figure looks different.",
    "  · {path}  → 재매칭 제안: {suggest}":
        "  · {path}  → suggested rematch: {suggest}",
    "아래 항목의 지문이 달라졌으나, 데이터 변경으로 설명됩니다:\n{lines}":
        "The fingerprints below changed, but the data change explains "
        "it:\n{lines}",
    "원본 스크립트가 변경되었습니다. 아래 항목은 다른 대상을 가리키고 있을 수 "
    "있습니다:\n{lines}":
        "The original script changed. The items below may now point at "
        "something else:\n{lines}",
    "스타일 모듈이 수동 편집되어 GUI로 되읽을 수 없습니다. 저장하면 "
    "덮어씁니다.\n  {issues}":
        "The style module was edited by hand and the GUI cannot read it "
        "back. Saving will overwrite it.\n  {issues}",
    "일부 override 적용 실패:\n  {failures}":
        "Some overrides could not be applied:\n  {failures}",

    # --- 미니 툴바 · 대상 대화상자 ------------------------------------------
    "모든 속성 보기": "Show all properties",
    "선택 해제": "Selection cleared",
    "현재 보기를 축 범위로": "Apply current view as axis range",
    "범위 적용": "Apply range",
    "지금 보는 확대·이동 범위를 축 범위(xlim/ylim)로 남깁니다.":
        "Keep the current zoom/pan as the axis range (xlim/ylim).",
    "보기가 축 범위와 같습니다.": "The view already matches the axis range.",
    "{n}개 선택됨": "{n} selected",
    "패널": "panel",
    "{where}를 해석하지 못했습니다: {err}": "could not parse {where}: {err}",
    "{where}에 ax를 받는 {func}() 함수가 없습니다.":
        "{where} has no {func}() function taking ax.",
    "{where}가 __file__을 씁니다. 병합 파일 안으로 옮기면 그 값이 병합 "
    "파일의 경로가 되어 다른 파일을 읽게 됩니다. 경로를 인자나 상수로 "
    "바꾼 뒤 다시 시도하세요.":
        "{where} uses __file__. Copied into the merge file that value becomes "
        "the merge file's own path, so it would read the wrong file. Turn the "
        "path into an argument or a constant and try again.",
    "{script}의 자리가 격자를 벗어납니다: ({r},{c}) {rs}x{cs} / 격자 {rows}x{cols}":
        "{script} falls outside the grid: ({r},{c}) {rs}x{cs} "
        "in a {rows}x{cols} grid",
    "{script}의 자리가 다른 패널과 겹칩니다: ({r},{c})":
        "{script} overlaps another panel at ({r},{c})",
    "격자 {rows}x{cols}에 패널 {n}개를 놓을 칸이 모자랍니다.":
        "A {rows}x{cols} grid has no room for {n} panels.",
    "{n}개 이동 중": "moving {n}",
    "고른 것들의 값이 서로 다릅니다": "The selected items have different values",
    "종이를 내용에 맞추지 못했습니다 ({n}번 시도). "
    "글자가 잘려 보이면 크기를 직접 조절하세요.":
        "Could not fit the paper to its content ({n} passes). "
        "If text looks clipped, set the size by hand.",
    "보기를 축 범위로 적용했습니다 ({n}건)":
        "Applied the view as the axis range ({n} changes)",
    "확대·이동은 보기만 바꿉니다. 남기려면 편집 › 현재 보기를 축 범위로.":
        "Zoom and pan only change the view. To keep it, use "
        "Edit > Apply current view as axis range.",
    "내보냄: {path} — 화면의 확대는 빼고 코드와 같은 그림으로 내보냈습니다.":
        "Exported: {path} — without the on-screen zoom, matching what the "
        "code produces.",
    "{name} 편집": "Edit {name}",
    "보조 눈금": "Minor ticks",
    "페이지": "Page",
    "범위": "Range",
    "눈금": "Ticks",
    "축선": "Axis line",
    "격자": "Grid",
    "범례": "Legend",
    "글자": "Text",
    "선": "Line",
    "점": "Points",
    "도형": "Shape",

    # --- 글꼴 고르기 ------------------------------------------------------
    "글꼴": "Font",
    "한글": "Korean",
    "복사": "Copy",
    "다시 찾기": "Scan again",
    "설치되지 않음": "not installed",
    "{name} (총칭)": "{name} (generic)",
    "설치할 수 있는 글꼴 더 보기": "More fonts you can install",
    "한글을 그릴 수 있습니다": "Can render Korean",
    "추천 글꼴이 모두 설치되어 있습니다.":
        "Every suggested font is already installed.",
    "figtune은 글꼴을 내려받지 않습니다. 아래 명령으로 설치한 뒤 "
    "'다시 찾기'를 누르세요.":
        "figtune does not download fonts. Install one with the command "
        "below, then press 'Scan again'.",
    "글꼴을 설치한 뒤 누르세요. matplotlib 목록을 다시 만듭니다.":
        "Press after installing a font. Rebuilds the matplotlib listing.",
    "현재 글꼴을 기본으로": "Make current the default",
    "기본 해제": "Clear default",
    "기본 글꼴: {name}": "Default font: {name}",
    "기본 글꼴: 지정 안 함 (matplotlib 기본값)":
        "Default font: none (matplotlib default)",

    # --- 한글 글꼴 안내 ---------------------------------------------------
    "한글 글꼴 없음": "No Korean font",
    "다시 보지 않기": "Don't show again",
    "이 환경에는 한글 글꼴이 없어 한국어 글자가 네모로 표시됩니다.":
        "This system has no Korean font, so Korean text renders as boxes.",
    "그래서 화면을 영어로 표시했습니다.":
        "The interface has been switched to English.",
    "그래서 한국어로 바꾸지 않았습니다.":
        "Korean was therefore not applied.",
    "아래 명령으로 글꼴을 설치한 뒤 figtune을 다시 실행하세요:\n\n  {cmd}":
        "Install a font with the command below, then restart "
        "figtune:\n\n  {cmd}",
    "시스템에 CJK 글꼴(예: Noto Sans CJK)을 설치한 뒤 figtune을 다시 "
    "실행하세요.":
        "Install a CJK font (for example Noto Sans CJK), then restart "
        "figtune.",

    # --- CLI: 도움말 ------------------------------------------------------
    "matplotlib figure를 GUI로 미세조정하고 코드로 남깁니다.":
        "Fine-tune a matplotlib figure in a GUI and keep the result as code.",
    "메시지 언어 (기본: 시스템 설정을 따름)":
        "message language (default: follow the system setting)",
    "스크립트를 실행할 인터프리터 (다른 venv/얼려진 앱인 경우)":
        "interpreter that runs the script (for a different venv or a "
        "frozen app)",
    "GUI로 편집 (PowerPoint 애드인이 호출)":
        "edit in the GUI (called by the PowerPoint add-in)",
    "시작 spec (없으면 디스크에서)":
        "starting spec (read from disk when omitted)",
    "저장 시 spec을 여기에도 기록": "also write the spec here on save",
    "저장 시 이미지를 여기에도 기록": "also write the image here on save",
    "GUI 없이 이미지만 생성": "render an image without opening the GUI",
    "pptx 안의 figtune 그림을 모두 재생성":
        "regenerate every figtune figure inside a pptx",
    "다른 파일로 저장 (기본: 덮어쓰기)":
        "write to a different file (default: overwrite)",
    "쓰지 않고 무엇이 바뀌는지만 보고":
        "report what would change without writing",
    "여러 패널 스크립트를 하나의 figure로 합침":
        "merge several panel scripts into a single figure",
    "패널 스크립트들 (배치 순서대로)": "panel scripts, in layout order",
    "생성할 병합 스크립트 (.py)": "merge script to generate (.py)",
    "패널 하나의 크기(인치). 기본 4x3":
        "size of one panel in inches (default 4x3)",
    "패널 라벨 서식. 기본 '({a})'. 끄려면 빈 문자열":
        "panel label format, default '({a})'; empty string turns it off",
    "모드 B가 불가능할 때 SVG 합성으로 대신 출력":
        "fall back to SVG composition when mode B is not possible",
    "생성 후 GUI를 연다": "open the GUI after generating",
    "정규형이 아닌 스크립트를 먼저 *_norm.py로 변환":
        "convert non-normalized scripts to *_norm.py first",
    "스크립트를 정규형으로 변환": "convert a script to the normal form",
    "변환하지 않고 판정만": "only report, do not convert",
    "원본을 덮어쓴다 (기본은 *_norm.py 생성)":
        "overwrite the original (default writes *_norm.py)",
    "alt text → spec / script 경로": "alt text → spec / script path",
    "alt text가 담긴 텍스트 파일": "text file holding the alt text",

    # --- CLI: 출력 --------------------------------------------------------
    "파일 없음: {path}": "no such file: {path}",
    "갱신": "updated",
    "변경예정": "would change",
    "데이터 수정 {n}": "{n} data changed",
    "추가 {n}": "{n} added",
    "사라짐 {n}": "{n} removed",
    "건너뜀 {label}: {why}": "skipped {label}: {why}",
    "경고: 지문 불일치 {n}건": "warning: {n} fingerprint mismatches",
    "불가": "no",
    " (이미 정규형)": " (already normalized)",
    "정규화  {src} → {dst}": "normalized  {src} → {dst}",
    "정규화 실패: {path}": "could not normalize: {path}",
    "--panel-size 형식은 WxH 입니다 (예: 4x3)":
        "--panel-size takes the form WxH (for example 4x3)",
    "\n원본을 고칠 수 없다면 --svg PATH 로 SVG 합성을 쓰세요. 다만 그 결과는 "
    "하나의 Figure가 아니며 통째로 편집할 수 없습니다.":
        "\nIf you cannot change the originals, use --svg PATH for SVG "
        "composition. Note that the result is not a single Figure and "
        "cannot be edited as a whole.",
    "{path}  (SVG 합성 — 하나의 Figure가 아닙니다)":
        "{path}  (SVG composition — not a single Figure)",
    "{path}  ({rows}×{cols}, 패널 {n}개)":
        "{path}  ({rows}×{cols}, {n} panels)",
    "평범한 matplotlib 스크립트입니다. figtune으로 열어 편집하세요:":
        "It is an ordinary matplotlib script. Open it in figtune to edit:",

    # --- selector -------------------------------------------------------
    "알 수 없는 selector: {path}": "unknown selector: {path}",
    "suptitle 없음": "no suptitle",
    "figure 범례 없음": "no figure legend",
    "{path} 없음": "{path} not found",
    "{path} 없음 (개수 {n})": "{path} not found ({n} available)",
    "axes[{i}] 없음 ({path})": "axes[{i}] not found ({path})",
    "spine {name} 없음": "spine {name} not found",
    "user text {name} 없음": "user text {name} not found",
    "해석 불가: {path}": "cannot resolve: {path}",
    "코드 표현식 불가: {path}": "no code expression for: {path}",

    # --- parse / session / runner ---------------------------------------
    "apply_style 함수를 찾을 수 없음": "no apply_style function found",
    "RCPARAMS 해석 실패": "could not parse RCPARAMS",
    "line {n}: 해석 못 한 대입문": "line {n}: unrecognized assignment",
    "line {n}: 단순 호출이 아닌 문장": "line {n}: not a plain call",
    "line {n}: 해석 못 한 호출": "line {n}: unrecognized call",
    "스크립트가 figure를 만들지 않았습니다.":
        "The script did not create a figure.",
    "열린 스크립트가 없습니다.": "No script is open.",
    "사용자 인터프리터에서 스크립트 실행 실패:\n{err}":
        "The script failed in your interpreter:\n{err}",
    "matplotlib 버전이 다릅니다 (스크립트 환경 {child}, figtune {ours}). "
    "Figure pickle은 버전에 결합되어 있어 안전하게 주고받을 수 없습니다. "
    "figtune을 같은 환경에 설치하거나 인프로세스 모드를 쓰세요.":
        "matplotlib versions differ (script environment {child}, figtune "
        "{ours}). A Figure pickle is tied to its version and cannot be "
        "transferred safely. Install figtune in the same environment or "
        "use in-process mode.",
    "Figure를 옮겨오지 못했습니다: {err}":
        "Could not transfer the Figure: {err}",

    # --- normalize -------------------------------------------------------
    "정규형으로 바꿀 수 있습니다.": "Can be converted to the normal form.",
    "정규형으로 바꿀 수 없습니다:\n  {reasons}":
        "Cannot be converted to the normal form:\n  {reasons}",
    "구문 오류: {err}": "syntax error: {err}",
    "이미 정규형입니다.": "Already in the normal form.",
    "변환 가능합니다.": "Conversion is possible.",
    "그리기 문장을 찾지 못했습니다.": "No drawing statement was found.",
    "모듈 수준 plt.subplots() 호출이 {n}개입니다. 정확히 하나여야 합니다.":
        "There are {n} module-level plt.subplots() calls. There must be "
        "exactly one.",
    "subplots()가 여러 축을 만듭니다. 이미 다패널 figure이므로 병합 대상이 "
    "아닙니다.":
        "subplots() creates several axes. This is already a multi-panel "
        "figure, so it is not a merge candidate.",
    "`fig, ax = plt.subplots(...)` 형태가 아닙니다.":
        "Not of the form `fig, ax = plt.subplots(...)`.",
    "{line}행: pyplot 상태 호출 plt.{attr}()은 어느 축을 가리키는지 알 수 "
    "없습니다. ax.{attr}(...) 형태로 바꾸세요.":
        "line {line}: the stateful pyplot call plt.{attr}() does not say "
        "which axes it means. Rewrite it as ax.{attr}(...).",
    "{line}행: figure 수준 호출 {attr}은 옮길 수 없습니다. 손으로 "
    "처리하세요.":
        "line {line}: the figure-level call {attr} cannot be moved. "
        "Handle it by hand.",
    "{line}행: 그리기 대상을 쓰는 문장이 단순 호출이나 대입이 아닙니다 "
    "(조건문·반복문은 자동 변환하지 않습니다).":
        "line {line}: the statement using the drawing target is neither a "
        "plain call nor an assignment (conditionals and loops are not "
        "converted automatically).",
    "{line}행: 그리기 대상을 그리기 외 용도로 씁니다(출력·계산 등). 함수 "
    "안으로 옮기면 실행 시점이 달라지므로 손으로 처리하세요.":
        "line {line}: the drawing target is used for something other than "
        "drawing (printing, computing, ...). Moving it into a function "
        "would change when it runs, so handle it by hand.",
    "{line}행: {names}은(는) plot(ax) 안으로 옮겨지는데 이 문장이 모듈 "
    "수준에서 씁니다.":
        "line {line}: {names} moves into plot(ax), but this statement uses "
        "it at module level.",

    # --- montage ---------------------------------------------------------
    "여백이 목표 크기보다 큽니다. target을 키우세요.":
        "The margins exceed the target size. Increase target.",
    "패널 {n}개는 {rows}×{cols} 격자에 넘칩니다.":
        "{n} panels do not fit in a {rows}×{cols} grid.",
    "SVG→PNG 변환에는 cairosvg가 필요합니다 (pip install cairosvg). 설치가 "
    "어려우면 벡터 없이 패널을 PNG로 합성하세요.":
        "SVG→PNG conversion needs cairosvg (pip install cairosvg). If you "
        "cannot install it, compose the panels as PNG without vectors.",
    "다음 스크립트는 합칠 수 없습니다:\n  {scripts}\n\n"
    "ax를 받는 함수를 노출하면 확실합니다:\n"
    "    def plot(ax):\n        ...\n"
    "    if __name__ == '__main__':\n"
    "        fig, ax = plt.subplots(); plot(ax)\n"
    "단독 실행도 그대로 되고 병합도 가능해집니다.":
        "These scripts cannot be merged:\n  {scripts}\n\n"
        "Exposing a function that takes ax makes it certain:\n"
        "    def plot(ax):\n        ...\n"
        "    if __name__ == '__main__':\n"
        "        fig, ax = plt.subplots(); plot(ax)\n"
        "Running it on its own still works, and merging becomes possible.",

    # --- 자동 감싸기 ------------------------------------------------------
    "해석하지 못했습니다: {err}": "could not parse it: {err}",
    "이미 ax를 받는 함수가 있습니다 — 감쌀 필요가 없습니다.":
        "it already has a function taking ax — no wrapping needed.",
    "축을 {n}개 만드는 스크립트입니다. 한 칸에 진짜 축으로 넣을 수 "
    "없습니다 — 칸 {n}개를 차지하게 하거나, 패널마다 파일을 나누세요.":
        "this script creates {n} axes. They cannot go into one cell as real "
        "axes — give it {n} cells, or split it into one file per panel.",

    # --- PowerPoint ------------------------------------------------------
    "payload 버전 {v}은 이 figtune보다 새롭습니다. 업데이트하세요.":
        "Payload version {v} is newer than this figtune. Please update.",
    "figtune payload를 읽지 못했습니다: {err}":
        "Could not read the figtune payload: {err}",
    "갱신 {n}건": "{n} updated",
    "건너뜀 {n}건": "{n} skipped",
    "데이터 변경 {n}건": "{n} with changed data",
    "스크립트를 찾을 수 없음: {path}": "script not found: {path}",
    "렌더 실패: {err}": "render failed: {err}",
    "figtune 도형이 아닙니다.": "Not a figtune shape.",
}
