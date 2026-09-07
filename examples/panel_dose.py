"""예제 패널: 용량-반응 (seaborn hue).

seaborn이 hue 범례를 만들려고 데이터 점이 0개인 artist를 남기는 경우다.
figtune 트리에서 그것들은 `(범례 전용)`으로 표시된다 — 색을 바꿔도 화면에
아무 일이 없는 이유를 알 수 있게.
"""
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

RNG = np.random.default_rng(7)


def plot(ax):
    groups = np.repeat(["low", "mid", "high"], 30)
    vals = np.concatenate([RNG.normal(m, 0.4, 30) for m in (1.0, 1.8, 2.9)])
    sns.scatterplot(x=RNG.uniform(0, 1, 90), y=vals, hue=groups, ax=ax)
    ax.set_xlabel("Exposure")
    ax.set_ylabel("Response")
    ax.set_title("Dose response")


if __name__ == "__main__":
    fig, ax = plt.subplots(figsize=(5, 3))
    plot(ax)
    fig.tight_layout()
    plt.show()
