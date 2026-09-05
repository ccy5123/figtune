# figtune

이미 그려진 matplotlib/seaborn figure를 GUI로 미세조정하고, 그 조정이
**재현 가능한 Python 코드로 남는** 데스크톱 도구.

```bash
pip install -e ".[gui]"
figtune plot_fig3.py
```

---

## 무엇을 하는가

입력은 항상 **준완성 figure**다. 이미 동작하는 플로팅 스크립트가 있고,
figtune은 그 결과물의 표현만 손본다.

**다루는 것** — 글꼴(종류·크기·굵기·색), 텍스트 내용과 위치, 임의 텍스트 삽입,
figure 크기, 선/마커 색과 크기, spine 표시와 오프셋, tick 방향·길이·간격,
grid, 범례 위치와 스타일, 축 범위와 스케일, 멀티패널 간격, (a)(b)(c) 패널 라벨,
PNG/PDF/SVG 내보내기.

**다루지 않는 것** — 원본 데이터, plot 종류, 시리즈 추가·삭제, 커브 피팅,
seaborn semantic(`hue`/`style`) 재매핑. 데이터나 함수가 바뀌어야 하는 작업은
범위 밖이다.

---

## 핵심 설계: 원본 코드를 고치지 않는다

범위가 표현으로 한정되므로 사용자의 플로팅 코드를 **읽지도 고치지도 않는다.**
스크립트를 그대로 실행해 살아있는 `Figure`를 얻고, 그 위에 override만 덧씌운다.

```
plot_fig3.py 실행 → Figure → GUI 편집 → spec → 코드 생성
```

산출물은 두 개다.

| 파일 | 역할 |
|---|---|
| `plot_fig3.figtune.yaml` | spec. 단일 원본. 손으로 읽고 고칠 수 있다 |
| `plot_fig3_style.py` | 생성된 override 모듈 |

원본 스크립트에는 **두 줄만** 추가된다 (그것도 사용자 확인을 받은 뒤에만).

```python
from plot_fig3_style import apply_style
apply_style(fig)
```

이 구조 덕분에 임의 Python을 파싱할 필요가 없다. 우리가 읽고 쓰는 코드는
우리가 생성한 영역 100%라서 왕복이 원리적으로 안전하다. 루프나 헬퍼 함수로
감싼 플로팅 코드도 문제되지 않는다 — 실행 결과만 보기 때문이다.

---

## 데이터는 어떻게 다루나

**figtune은 데이터를 들고 있지 않다.** 스크립트가 들고 있고, figtune은 그것을
다시 돌린다. Origin이 OLE로 임베드할 때 그래프와 데이터 시트를 대상 파일에
저장하는 것과 정반대다.

| | Origin (임베드) | figtune |
|---|---|---|
| 덱/문서에 들어가는 것 | 그래프 + 원본 데이터 | 그림 + spec(≈1KB) + 출처 지문 |
| 파일 크기 | 데이터만큼 불어남 | 거의 그대로 |
| 데이터 갱신 | Origin에서 수동 재작업 | 스크립트 재실행 |
| 외부 배포 | 원본 데이터가 함께 나감 | 그림과 스타일만 나감 |

이 선택에는 구멍이 하나 따라온다. 데이터를 품지 않으므로 **어떤 데이터에서
나온 그림인지 알 수 없다.** 3월 슬라이드와 6월 슬라이드가 똑같이 생겼는데
다른 데이터일 수 있다.

그래서 데이터 대신 **데이터의 지문**을 남긴다. 스크립트가 실행 중 읽은 파일을
`sys.addaudithook`으로 포착해 경로·크기·SHA-256을 spec에 기록한다. 인프로세스
모드와 `--python` 서브프로세스 모드 양쪽에서 동작한다.

```bash
figtune refresh deck.pptx --check
# 변경예정  slide 3 / plot_fig3.py  [데이터 수정 1]
```

`--check`는 덱을 건드리지 않고 무엇이 바뀔지만 보고한다.

### 기준점이 둘이다

| 무엇 | 무엇을 기준으로 | 왜 |
|---|---|---|
| 스크립트 경로 | **덱(pptx) 위치** | 덱이 스크립트를 가리켜야 하므로 |
| 스크립트가 읽는 데이터 | **스크립트 위치** | 실행 시 스크립트 디렉토리로 chdir |
| 기록된 데이터 출처 | **스크립트 위치** | 프로젝트를 옮겨도 지문이 유지되도록 |

```
project/
├── slides/deck.pptx          →  script = "../analysis/plot_a.py"
└── analysis/
    ├── plot_a.py             →  pd.read_csv("data.csv")
    └── data.csv              →  기록: "data.csv"
```

`Payload.for_deck(script, deck, spec)`가 덱 기준 상대경로를 자동 계산한다.
다른 드라이브처럼 상대경로가 불가능하면 절대경로로 남긴다.

프로젝트를 폴더째 옮겨도 refresh가 그대로 동작한다. 경로를 절대경로로
기록하면 같은 파일이 '사라짐 + 추가됨'으로 잡혀 오경보가 나는데, 오경보는
경고 전체를 무의미하게 만든다. 내용(SHA-256)이 같고 경로만 다르면 '옮겨진
것'으로 보고 변경으로 치지 않는다.

### 데이터 변경과 코드 변경을 구분한다

지문 검증은 원래 "원본 스크립트가 바뀌었다"를 잡기 위한 것이었는데, 데이터가
바뀌어도 똑같이 어긋난다. 둘을 같은 경고로 묶으면 사용자가 경고를 무시하게
되고, 그러면 정작 위험한 경우 — 인덱스가 밀려 엉뚱한 선에 색이 칠해지는 것 —
을 놓친다. 그래서 출처 지문으로 원인을 갈라 다른 문구를 띄운다.

- 데이터만 바뀜 → "입력 데이터가 바뀌었습니다. 그림이 달라지는 것은 정상입니다"
- 코드가 바뀜 → "원본 스크립트가 변경되었습니다. 재매칭이 필요합니다"

### 하지 않는 것

데이터 편집, 필터링, 피팅은 범위 밖이다. 그건 스크립트가 할 일이다.
figtune이 데이터를 만지기 시작하면 "이 도구는 표현만 건드린다"는 전제가
무너지고, 원본 코드를 파싱하지 않아도 되는 이유도 함께 사라진다.

---

## 정규형

figtune의 모든 상태는 정규형으로만 존재한다. 정규형을 정해 두면 spec 비교,
git diff, 왕복 검증이 전부 기계적으로 가능해진다.

### spec 정규형

**보장하는 것** (전부 테스트로 확인한다)

| 성질 | 내용 |
|---|---|
| 멱등 | `N(N(x)) = N(x)` |
| 결정성 | 같은 내용은 항상 같은 바이트로 직렬화 |
| 닫힘 | 모든 조작의 결과가 다시 정규형 |
| 왕복 | `parse(codegen(N(s))) = N(s)` |

접는 규칙: 색은 소문자 hex, `solid`→`-`, `dashed`→`--`, 빈 마커 표기는
`none`, 굵기 `700`→`bold`, 범례 위치 정수 코드 `2`→`upper left`, tuple→list,
`None`과 빈 dict 제거, 해석 불가한 selector 제거. 키는 **적용 순서**로
정렬한다 — 적용 순서와 정렬 순서가 어긋나면 "저장한 대로 다시 적용된다"는
보장이 깨지므로 하나의 표(`canon.KIND_ORDER`)를 apply·codegen·canon이 함께
쓴다.

**보장하지 않는 것.** 의미적 최소화는 하지 않는다. 즉 "그림이 같으면 spec도
같다"는 성립하지 않는다. 그러려면 스크립트가 이미 그린 값과 대조해 중복
override를 지워야 하는데, 그러면 spec이 스크립트 내용에 의존하게 된다.
스크립트가 바뀌는 순간 사용자가 명시한 지정이 조용히 사라진다 — figtune에서
가장 위험한 실패다. 그래서 정규형은 **구문적**이다.

**두 단계로 적용한다.** 편집 중에는 override 표만 정규화하고, user text id
재부여는 open/save 경계에서만 한다. 편집 도중 id가 밀리면 GUI가 들고 있는
selector(`ax0.text:t002`)가 다른 텍스트를 가리키게 되기 때문이다.

### 스크립트 정규형

```python
<imports 및 데이터 준비>

def plot(ax):
    ...

if __name__ == "__main__":
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=...)
    plot(ax)
```

```bash
figtune normalize plot_a.py --check     # 판정만
figtune normalize plot_a.py             # plot_a_norm.py 생성
figtune merge *.py -o quad.py --normalize
```

원본은 기본적으로 덮어쓰지 않는다. `--in-place`를 명시해야 한다.

**인식 가능한 부분집합에서만 동작한다.** 임의의 Python을 정규형으로 바꾸는
것은 일반적으로 불가능하다. 벗어나면 무엇이 몇 행에서 걸렸는지 알리고
멈춘다 — 추측해서 고치면 사용자의 그림이 소리 없이 달라진다.

**받아들이는 형태**

- `ax.plot(...)` 같은 그리기 호출
- `im = ax.imshow(...)`, `ax2 = ax.twinx()` 같은 단순 대입
- 대입으로 묶인 이름의 후속 그리기 (`ax2.plot(...)`, `cb.set_label(...)`).
  그리기 대상 집합이 전이적으로 자란다
- `fig.colorbar(...)` → `ax.figure.colorbar(...)`로 바꿔 옮긴다. colorbar는
  인자로 받은 축에 붙으므로 병합 격자에서도 제자리를 지킨다
- `plt.show()`, `fig.tight_layout()` 등 레이아웃·출력 호출은 버린다
  (단독 실행 블록과 병합 스크립트가 대신 처리한다)

**거부하는 형태**

- `subplots()`가 여러 축을 만드는 경우, 호출이 둘 이상인 경우, 아예 없는
  경우(seaborn `relplot` 등)
- 그리기 문장이 조건문·반복문 안에 있는 경우
- `fig.suptitle(...)` — figure 전체의 것이라 병합하면 패널마다 서로
  덮어써서 마지막 것만 남는다
- `plt.title(...)` 같은 pyplot 상태 호출 — 어느 축을 가리키는지 알 수 없다
- `print(im.get_array().max())`처럼 그리기 대상을 **그리기 외 용도**로 쓰는
  문장. 옮기면 실행 시점이 import에서 `plot()` 호출로 바뀐다
- 함수 안으로 옮겨질 이름을 모듈 수준에서 쓰는 경우 (NameError 예방)

판단 기준은 **문장의 바깥쪽 호출**이다. `cb.set_label(...)`은 그리기지만
`print(im.get_array())`는 안쪽에 대상 호출이 있어도 문장 자체는 출력이다.

---

## 여러 figure 합치기

두 가지 모드가 있고, **무엇을 내놓는지가 서로 다르다.** 어느 쪽인지 알고
쓰는 것이 중요하다.

| | 모드 A · montage | 모드 B · subplot |
|---|---|---|
| 원본 수정 | 불필요 | `plot(ax)` 노출 필요 |
| 산출물 | SVG 합성물 | **진짜 Figure + 평범한 파이썬 스크립트** |
| 하나의 `ax` 객체인가 | 아니다 | 그렇다 |
| 편집 단위 | 패널별로 따로 | 통째로 |
| figtune 의존 | 있다 | 없다 |

### 모드 B가 가능하면 그쪽을 쓴다

패널 스크립트를 이렇게 바꾸면 된다. 단독 실행도 그대로 된다.

```python
def plot(ax):
    ax.plot(...)
    ax.set_xlabel('Time (h)')

if __name__ == '__main__':
    fig, ax = plt.subplots(); plot(ax)
```

그러면 figtune이 병합 스크립트를 생성한다. 결과는 평범한 matplotlib
Figure이므로 figtune으로 열어 통째로 편집할 수 있고, 생성된 `*_style.py`는
figtune 없이 돌아간다. 조건을 만족하지 않으면 무엇이 빠졌는지 알리고
중단한다 — 조용히 모드 A로 떨어지면 어느 산출물을 보고 있는지 알 수 없다.

병합 스크립트가 만든 (a)(b)(c) 라벨도 편집 대상이다. 더 넓게는, 사용자
스크립트가 `ax.text()`로 넣은 주석이 전부 트리에 `ax0.txt0` 형태로 나타난다.
다만 **지울 수는 없다** — 지워도 재실행하면 되살아나기 때문이다. 감추려면
`visible=False`를 쓰고, 그것도 코드로 남는다.

### 모드 A는 왜 axes를 옮기지 않는가

matplotlib은 figure 사이의 axes 이동을 지원하지 않는다. `ax.figure = other`
도 `ax.set_figure(other)`도 transform 체인이 낡은 채 남아 눈금이 뭉개지고
내용이 잘린다. 실측으로 확인했다. 그래서 모드 A는 SVG 레벨에서 합성한다.

**axes 상자를 기준으로 정렬한다.** 단순 타일링은 논문 그림으로 못 쓴다.
y축 라벨 길이가 다르면 패널마다 그림틀 위치가 어긋나기 때문이다. 각 패널의
axes 위치는 알 수 있으므로(`ax.get_position()` × figure 크기) 열마다 왼쪽
모서리를, 행마다 위 모서리를 맞춘다.

**크기는 배율이 아니라 재렌더로 맞춘다.** 균일 배율은 종횡비가 다른 패널의
가로세로를 동시에 맞출 수 없고, 비균일 배율은 글씨를 찌그러뜨린다. 그래서
축 라벨이 차지하는 여백은 인치 단위로 두고 그림틀만 목표 크기로 다시 잡은 뒤
재렌더한다. 배율 1로 정확히 일치한다.

```python
from figtune.core.montage_build import MontageSpec, PanelRef, build

ms = MontageSpec(rows=2, cols=2, panels=[PanelRef(script=f"p{i}.py")
                                         for i in range(4)])
result = build(ms, base_dir="analysis/")     # (a)(b)(c)(d) 자동
```

---

## 3D 그래프

3D axes를 선택하면 고도각·방위각·롤·확대 조절이 나타난다. `view_init`은
일부 인자만 주면 나머지를 초기값으로 되돌리므로 배치로 적용한다 — 범례,
제목 여백과 같은 함정이다.

---

## 안전장치

**지문 검증.** `ax0.line1` 같은 인덱스 주소는 원본 스크립트가 바뀌면 **조용히**
어긋난다. 색을 바꾸려던 선이 다른 선이 되는 식이다. 각 artist에 지문(점 개수,
첫/끝 좌표, 라벨)을 저장하고 로드할 때 대조한다. 불일치는 경고하고, 라벨 기준
재매칭 후보를 제안하되 **사용자 승인 없이 적용하지 않는다.**

**null = 건드리지 않음.** spec에 명시한 키만 override 코드가 된다. 원본
스크립트가 설정한 값이 GUI를 한 번 열었다는 이유로 덮이지 않는다.

**수동 편집 감지.** 생성된 스타일 모듈에 로직(if/for/변수 대입)을 넣으면 파싱을
포기하고 읽기 전용으로 전환한다. 조용히 뭉개지 않는다.

---

## 구조

```
figtune/
├── core/              # UI 무관 · 순수 Python · 의존성은 matplotlib + pyyaml 뿐
│   ├── props.py       # 프로퍼티 레지스트리 — GUI·적용·생성·파싱의 단일 참조점
│   ├── selector.py    # 주소 지정 (ax0.line1, ax0.spine:top, ax0.xtick.major)
│   ├── spec.py        # 스키마 + YAML 직렬화
│   ├── fingerprint.py # 지문 생성·대조
│   ├── introspect.py  # Figure → 노드 트리
│   ├── apply.py       # spec → 살아있는 Figure
│   ├── codegen.py     # spec → 스타일 모듈
│   ├── parse.py       # 스타일 모듈 → spec (표준 ast, libcst 불필요)
│   ├── runner.py      # 스크립트 실행 → Figure 회수
│   ├── history.py     # undo/redo
│   └── session.py     # 파사드. 프론트엔드는 이것만 호출
├── ui/qt/             # PySide6 어댑터
└── cli.py
```

`core`는 PySide6를 import하지 않는다. 이 경계가 나중에 웹이나 PowerPoint
어댑터를 붙일 수 있게 하는 유일한 조건이다.

속성을 하나 추가하려면 `props.REGISTRY`만 고치면 된다. 인스펙터 위젯, 코드
생성, 파싱이 전부 거기서 파생된다.

---

## 실행 모드

| 모드 | 동작 | 언제 |
|---|---|---|
| 인프로세스 (기본) | 스크립트를 figtune과 같은 인터프리터에서 `exec` | figtune이 분석 환경에 설치된 경우 |
| 서브프로세스 (`--python`) | 지정한 인터프리터에서 실행 후 Figure를 pickle로 회수 | figtune이 다른 venv나 얼려진 앱인 경우 |

```bash
figtune plot_fig3.py --python .venv/bin/python
```

**왜 필요한가.** "이 스크립트는 작동한다"는 것은 *사용자 환경*에 대한 사실이지
figtune의 인터프리터에 대한 사실이 아니다. figtune이 별도 venv나 PyInstaller
번들 안에 있으면 `import seaborn`은 사용자의 site-packages가 아니라 앱의
`sys.path`를 뒤진다. 그럴 때 스크립트를 사용자 환경에서 돌리고 결과 Figure만
받아오면 해결된다.

**제약.** Figure pickle은 matplotlib 버전에 결합되어 있다. 양쪽 minor 버전이
다르면 실행을 거부하고 이유를 알린다 — 조용히 깨진 Figure를 넘기지 않는다.

---

## 알려진 제약

- **임의 코드 실행.** 인프로세스 모드는 스크립트를 격리 네임스페이스에서
  `exec`한다. 라이브 프리뷰에 필요하지만 신뢰할 수 있는 파일만 열어야 한다.
  서브프로세스 모드는 별도 프로세스라 이 점에서 더 안전하다.
- **화면 dpi와 출력 dpi는 별개다.** spec의 `dpi`는 export에만 쓰이고, 화면은
  뷰포트에 맞춘 표시 배율로 그린다. 같은 값으로 묶으면 figure가 캔버스를
  넘어가 잘린다.
- **rcParams는 소급 적용되지 않는다.** 이미 만들어진 artist에는 반영되지
  않으므로 개별 override로 처리한다.
- `constrained_layout`이 켜진 상태의 수동 위치 조정은 충돌할 수 있다.
- seaborn artist는 순서가 문서화되어 있지 않다. 지문 검증이 이를 보완한다.

---

## 테스트

```bash
python -m pytest tests/ -q
```

가장 중요한 세 가지를 못박아 두었다.

1. **왕복 무손실** — spec → 코드 → spec 에서 값이 하나도 사라지지 않는다.
2. **생성 코드 실제 실행** — 훅이 걸린 스크립트를 별도 프로세스에서 돌린
   결과가 GUI 렌더와 바이트 단위로 같다. 문법만 맞고 동작이 다르면 도구
   전체가 거짓말이 된다.
3. **편집 순서 무관성** — `ax.set_title(text, pad=)`은 내부에서 폰트 속성을
   rcParams 기본값으로 되돌린다. 그래서 '굵게 → 여백' 순으로 편집하면 굵기가
   조용히 사라졌다. 편집 중 화면과 재실행 결과가 갈리는 버그라 회귀 테스트로
   고정했다.

---

## PowerPoint 연동

IguanaTeX의 구조를 따른다. 그림과 함께 **그것을 만든 소스를 도형에 심어두고**,
도형을 골라 다시 편집한다. 소스는 도형 alt text에 압축되어 들어가므로(보통
1KB 미만) 프레젠테이션을 옮겨도 따라다닌다. figtune이 없는 컴퓨터에서도 발표는
되고, 편집만 figtune을 요구한다.

가장 쓸모 있는 기능은 **덱 전체 갱신**이다. 데이터나 모델이 바뀌면 슬라이드에
박힌 그림을 하나씩 다시 만들어 붙이는 대신 한 줄로 끝낸다.

```bash
figtune refresh deck.pptx
```

각 그림의 원본 스크립트를 다시 돌려 재생성하고, **위치·크기·회전·z순서를
보존한 채** 갈아끼운다. 발표자가 슬라이드에서 손으로 맞춰둔 배치를 재생성
때문에 잃으면 도구를 쓸 이유가 없다. 스크립트를 못 찾으면 그 그림만 건너뛰고
사유를 보고한다.

PowerPoint 없이 python-pptx만으로도 쓸 수 있다.

```python
from figtune.office import pptx_link as PL

PL.insert(slide, "fig.png",
          PL.Payload(script="plot_fig3.py", spec=spec, dpi=300),
          left=Inches(1), top=Inches(1), width=Inches(6))
```

### 공유 안전성

슬라이드에는 **진짜 그림이 박힌다.** spec은 alt text에 메타데이터로만 얹히고,
이미지는 pptx 안에 임베드된다(외부 링크가 아니다). 따라서 figtune이 없는
컴퓨터에서도 그냥 사진으로 보이고 발표된다. IguanaTeX와 같은 성질이며,
테스트로 잠가두었다 — 외부 링크로 바뀌면 실패한다.

### 벡터 출력 (선택, 렌더링 미검증)

`vector=True`로 넣으면 SVG를 임베드하되 **PNG 대체본을 함께** 넣는다.
OOXML은 이를 다음 구조로 담는다.

```xml
<a:blip r:embed="rIdPng">              <!-- 구형 뷰어가 보는 것 -->
  <a:extLst>
    <a:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}">
      <asvg:svgBlip r:embed="rIdSvg"/> <!-- PowerPoint 365가 그리는 것 -->
    </a:ext>
  </a:extLst>
</a:blip>
```

SVG를 모르는 뷰어는 PNG를 보므로 공유는 여전히 안전하다. 패키지 구조(파트,
관계, 콘텐츠 타입, 확장 GUID)는 테스트로 확인했으나 **실제 PowerPoint에서
벡터로 렌더되는지는 확인하지 못했다** — 리눅스 컨테이너에 PowerPoint가 없다.
기본값은 PNG이며 벡터는 명시적으로 켜야 한다.

SVG와 PNG는 반드시 같은 Session에서 뽑는다. 따로 렌더하면 난수나 시각에
의존하는 스크립트에서 두 파일의 내용이 어긋난다.

### 애드인 (미검증)

`figtune/office/FigTune.bas`가 `.ppam` VBA 애드인 소스다. 리본에서 새 그림
삽입 / 기존 그림 편집 / 덱 갱신을 제공한다. **이 VBA는 PowerPoint에서 실행
검증된 적이 없다** — 리눅스에서 작성되었다. 파이썬 쪽(`edit`/`render`/`refresh`
서브커맨드와 `vba_bridge`)은 테스트를 통과했으니, VBA는 Windows에서 직접
돌려보며 다듬어야 한다. 특히 `Shell` 대기 처리와 경로 인용을 확인할 것.

VBA에는 zlib이 없다. payload 인코딩을 VBA에서 재구현하면 파이썬 쪽과 어긋날
위험이 커서, `figtune.office.vba_bridge`에 위임하고 애드인은 파일만 주고받는다.

---

## 로드맵

- **v1** — 스타일 프로파일 저장·재적용, 여러 figure 배치 처리
- **v2** — seaborn semantic 레이어, 웹 프론트엔드 어댑터
- **v3** — VBA 애드인 실검증, Mac 지원, EMF 벡터 출력(Inkscape 경유)

MIT
