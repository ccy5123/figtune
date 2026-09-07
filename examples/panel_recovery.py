"""예제 패널: 배출 곡선. y축 라벨이 일부러 짧다.

패널마다 y라벨 길이가 다르면 단순 타일링으로는 그림틀이 어긋난다.
figtune의 모드 A는 axes 상자를 기준으로 맞추고, 모드 B는 하나의 격자에
그리므로 둘 다 이 문제를 피한다.
"""
import numpy as np
import matplotlib.pyplot as plt

RNG = np.random.default_rng(11)


def plot(ax):
    t = np.linspace(0, 72, 30)
    for k, label in ((0.05, "slow"), (0.12, "fast")):
        y = 3.5 * np.exp(-k * t) + RNG.normal(0, 0.05, t.size)
        ax.plot(t, y, "o-", markersize=3, label=label)
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("C")
    ax.set_title("Elimination")
    ax.legend(frameon=False)


if __name__ == "__main__":
    fig, ax = plt.subplots(figsize=(5, 3))
    plot(ax)
    fig.tight_layout()
    plt.show()
