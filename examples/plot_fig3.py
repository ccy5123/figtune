"""예제: 멀티패널 figure. figtune은 이 파일을 절대 수정하지 않는다."""
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

rng = np.random.default_rng(42)
t = np.linspace(0, 48, 24)
obs = 3.5 * (1 - np.exp(-0.09 * t)) + rng.normal(0, 0.12, t.size)
pred = 3.5 * (1 - np.exp(-0.09 * t))

fig, axes = plt.subplots(1, 2, figsize=(8, 3.2))

axes[0].plot(t, obs, "o", label="Observed", markersize=4)
axes[0].plot(t, pred, "-", label="DEB-TK")
axes[0].set_xlabel("Time (h)")
axes[0].set_ylabel("Concentration")
axes[0].set_title("Uptake")
axes[0].legend()

groups = np.repeat(["low", "mid", "high"], 30)
vals = np.concatenate([rng.normal(m, 0.4, 30) for m in (1.0, 1.8, 2.9)])
sns.scatterplot(x=rng.uniform(0, 1, 90), y=vals, hue=groups, ax=axes[1])
axes[1].set_xlabel("Exposure")
axes[1].set_ylabel("Response")
axes[1].set_title("Dose response")

fig.tight_layout()
plt.show()
