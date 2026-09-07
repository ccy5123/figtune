"""예제 패널: 흡수 곡선.

`plot(ax)`를 노출하는 형태다. 이 한 가지만 지키면 figtune이 이 파일을
다른 패널들과 하나의 figure로 합칠 수 있다. `__main__` 블록이 있으므로
단독 실행도 그대로 된다.

figtune은 이 파일을 절대 수정하지 않는다.
"""
import numpy as np
import matplotlib.pyplot as plt

RNG = np.random.default_rng(42)
KE = 0.09                      # 흡수 속도 상수 (1/h)
PLATEAU = 3.5                  # 정상상태 농도


def plot(ax):
    t = np.linspace(0, 48, 24)
    pred = PLATEAU * (1 - np.exp(-KE * t))
    obs = pred + RNG.normal(0, 0.12, t.size)

    ax.plot(t, obs, "o", label="Observed", markersize=4)
    ax.plot(t, pred, "-", label="DEB-TK")
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("Concentration (ug/g)")
    ax.set_title("Uptake")
    ax.legend()


if __name__ == "__main__":
    fig, ax = plt.subplots(figsize=(5, 3))
    plot(ax)
    fig.tight_layout()
    plt.show()
