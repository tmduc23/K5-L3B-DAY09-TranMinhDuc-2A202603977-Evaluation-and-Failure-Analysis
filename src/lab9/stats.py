"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _norm(x: str) -> str:
    return str(x).strip().upper()


# Đếm 4 ô
def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError("human and judge must have the same length")
    c = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for h, j in zip(human, judge):
        h_pos, j_pos = _norm(h) == POS, _norm(j) == POS
        if h_pos and j_pos:
            c["tp"] += 1
        elif not h_pos and j_pos:
            c["fp"] += 1
        elif h_pos and not j_pos:
            c["fn"] += 1
        else:
            c["tn"] += 1
    return c



def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    c = confusion(human, judge)
    p_den, r_den = c["tp"] + c["fp"], c["tp"] + c["fn"]
    precision = c["tp"] / p_den if p_den else 0.0
    recall = c["tp"] / r_den if r_den else 0.0
    return precision, recall


# mức đồng thuận sau khi trừ phần trùng hợp ngẫu nhiên
def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    c = confusion(human, judge)
    n = sum(c.values())
    if n == 0:
        raise ValueError("kappa undefined: no rows")
    p_o = (c["tp"] + c["tn"]) / n
    h_fail = (c["tp"] + c["fn"]) / n          # tỉ lệ người nói FAIL
    j_fail = (c["tp"] + c["fp"]) / n          # tỉ lệ judge nói FAIL
    p_e = h_fail * j_fail + (1 - h_fail) * (1 - j_fail)
    if p_e >= 1 - 1e-12:                      # so sánh float an toàn
        raise ValueError("kappa undefined: chance agreement is 1 (constant labels)")
    return (p_o - p_e) / (1 - p_e)


# hiệu chỉnh tỉ lệ lỗi quan sát được
def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    den = sensitivity + specificity - 1
    if den <= 0:
        return min(1.0, max(0.0, observed_rate))
    est = (observed_rate + specificity - 1) / den
    return min(1.0, max(0.0, est))



def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""    
    import numpy as np
    from scipy.stats import bootstrap

    a_arr, b_arr = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a_arr.shape == b_arr.shape and np.array_equal(a_arr, b_arr):
        return 0.0, 0.0, 0.0
    res = bootstrap((a_arr, b_arr),
                    lambda x, y, axis=-1: np.mean(x, axis=axis) - np.mean(y, axis=axis),
                    paired=True, vectorized=True, n_resamples=n_resamples, method="percentile",
                    confidence_level=confidence, rng=np.random.default_rng(rng))
    ci = res.confidence_interval
    return float(a_arr.mean() - b_arr.mean()), float(ci.low), float(ci.high)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    # TODO M6
    raise NotImplementedError


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    # TODO M6
    raise NotImplementedError
