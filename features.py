import numpy as np
from collections import deque

class SpectralFeatures:
    def __init__(self, target_bins=128, history=300):
        self.target_bins = int(target_bins)
        self.spec_hist = deque(maxlen=history)
        self.energy_hist = deque(maxlen=history)

    def _resample(self, v):
        v = np.asarray(v, dtype=np.float32).ravel()
        n = v.size
        if n == self.target_bins:
            return v
        x_old = np.linspace(0.0, 1.0, n, dtype=np.float32)
        x_new = np.linspace(0.0, 1.0, self.target_bins, dtype=np.float32)
        return np.interp(x_new, x_old, v)

    def update(self, v):
        v = self._resample(v)
        x = np.log1p(v)

        if self.spec_hist:
            m = float(np.mean(np.abs(x - self.spec_hist[-1])))
        else:
            m = 0.0
        self.spec_hist.append(x)

        E = float(np.mean(x))
        self.energy_hist.append(E)
        arr = np.array(self.energy_hist, dtype=np.float32)
        base = np.percentile(arr, 20) if len(arr) > 20 else (float(np.mean(arr)) if len(arr) else E)
        mad = float(np.median(np.abs(arr - np.median(arr)))) if len(arr) else 0.0
        mad = 1e-6 if mad == 0.0 else mad
        z = (E - base) / (1.4826 * mad)
        presence = float(1.0 / (1.0 + np.exp(-z)))

        idx = np.arange(self.target_bins, dtype=np.float32)
        w = x + 1e-6
        centroid = float((idx * w).sum() / w.sum())
        spread = float(np.sqrt(((idx - centroid) ** 2 * w).sum() / w.sum()))
        t = self.target_bins // 3
        p_lo = float(w[:t].sum() / w.sum())
        p_mid = float(w[t:2*t].sum() / w.sum())
        p_hi = float(w[2*t:].sum() / w.sum())

        return {"presence":presence,"motion":m,"centroid":centroid,"spread":spread,"p_lo":p_lo,"p_mid":p_mid,"p_hi":p_hi}
