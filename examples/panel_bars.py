"""예제 패널: 막대. patches가 그룹으로 묶여 트리에 나오는 경우다."""
import numpy as np
import matplotlib.pyplot as plt

TREATMENTS = ("control", "low", "mid", "high")
MEANS = (1.0, 1.4, 2.2, 3.1)
ERRORS = (0.12, 0.15, 0.21, 0.28)


def plot(ax):
    x = np.arange(len(TREATMENTS))
    ax.bar(x, MEANS, yerr=ERRORS, capsize=3)
    ax.set_xticks(x)
    ax.set_xticklabels(TREATMENTS)
    ax.set_ylabel("Body burden")
    ax.set_title("By treatment")


if __name__ == "__main__":
    fig, ax = plt.subplots(figsize=(5, 3))
    plot(ax)
    fig.tight_layout()
    plt.show()
