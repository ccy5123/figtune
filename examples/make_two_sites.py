"""데이터가 서로 다른 곳에 있는 패널 둘을 만든다 — 합치기 시험용.

figtune이 이런 구조를 만든다:

    <목적지>/
      siteA/  uptake.py  uptake.csv     ← 'uptake.csv'를 상대 경로로 읽는다
      siteB/  dose.py    dose.csv       ← 'dose.csv'를  상대 경로로 읽는다
      paper/                            ← 병합 결과를 둘 만한 빈 폴더

상대 경로는 실행하는 파일 기준으로 풀린다. 그래서 이 둘을 합칠 때 병합
파일을 어디에 두든 한쪽은 데이터를 못 찾는다. figtune이 만들기 전에 어느
패널이 왜 깨지는지 알려주는지 확인하는 것이 이 시나리오의 목적이다.

    python examples/make_two_sites.py /tmp/lab
    figtune /tmp/lab/siteA/uptake.py

figtune은 스크립트 폴더로 옮겨 실행하므로 어디서 불러도 열린다. 반면 맨손
`python`은 cwd 기준이라 그 폴더에서 돌려야 한다 — 상대 경로가 무엇에
걸리는지가 이 시나리오의 전부다.

그 다음 GUI에서:
    Ctrl+O 로 siteB/dose.py 를 연다
    Ctrl+M → 1행 2열 → 두 칸을 채운다 → 저장하고 종료
    저장 위치를 paper/ 로 하면 경고가 둘, siteA/ 로 하면 하나가 뜬다.

경고대로 데이터 옆(siteA/)에 저장해도 siteB 쪽은 못 찾는다. 해법은 둘 중
하나다 — 데이터를 한곳에 모으거나, 스크립트에서 절대 경로를 쓰는 것.
"""
import sys
from pathlib import Path

PANEL = '''import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv({data!r})          # 상대 경로 — 이 파일 옆을 본다


def plot(ax):
    ax.plot(df.x, df.y, {style!r})
    ax.set_xlabel('x')
    ax.set_ylabel({ylab!r})
    ax.set_title({title!r})


if __name__ == '__main__':
    fig, ax = plt.subplots(figsize=(4, 3))
    plot(ax)
    fig.tight_layout()
    plt.show()
'''

SITES = [
    ("siteA", "uptake", "0,0\n1,1.8\n2,2.9\n3,3.4\n", "o-",
     "Concentration", "Site A uptake"),
    ("siteB", "dose", "0,1.0\n1,1.6\n2,2.4\n3,3.3\n", "s--",
     "Response", "Site B dose"),
]


def build(dest: Path) -> None:
    for folder, stem, rows, style, ylab, title in SITES:
        d = dest / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{stem}.csv").write_text("x,y\n" + rows, encoding="utf-8")
        (d / f"{stem}.py").write_text(
            PANEL.format(data=f"{stem}.csv", style=style, ylab=ylab,
                         title=title), encoding="utf-8")
    (dest / "paper").mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "two_sites_demo")
    build(dest)
    a = dest / "siteA" / "uptake.py"
    print(f"{dest} 에 만들었습니다.\n")
    # 상대 경로는 cwd 기준으로 풀린다. 맨손 python은 그 폴더에서 해야 하고,
    # figtune은 스크립트 폴더로 옮겨 실행하므로 어디서든 열린다.
    print("패널을 단독 실행하려면 그 폴더에서:")
    print(f"  cd {dest / 'siteA'} && python uptake.py\n")
    print("figtune은 어느 위치에서 불러도 열립니다:")
    print(f"  figtune {a}\n")
    print("합치기를 시험하려면 그 뒤에:")
    print("  Ctrl+O 로 siteB/dose.py 를 열고, Ctrl+M → 1행 2열 → 두 칸을 채운 뒤")
    print("  저장 위치를 paper/ 로 해 보세요. 경고가 둘 뜹니다.")
