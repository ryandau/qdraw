"""
Randomness statistics for a bit string.

Min-entropy estimators follow NIST SP 800-90B (most common value, 6.3.1;
Markov, 6.3.3). These are estimates of how unpredictable each bit is, which is
the quantity that matters for fairness. Shannon entropy is reported too but is
nearly always close to 1 and says little on its own.
"""
from __future__ import annotations

from math import log2, sqrt
from typing import Dict, List, Optional, Sequence


def ones_fraction(bits: str) -> float:
    return bits.count("1") / len(bits) if bits else float("nan")


def shannon_entropy_per_bit(bits: str) -> float:
    p = ones_fraction(bits)
    if p in (0.0, 1.0):
        return 0.0
    return -(p * log2(p) + (1 - p) * log2(1 - p))


def min_entropy_mcv(bits: str) -> float:
    """Most Common Value estimate (SP 800-90B 6.3.1), 99% upper bound on p."""
    L = len(bits)
    if L < 2:
        return 0.0
    p_hat = max(ones_fraction(bits), 1 - ones_fraction(bits))
    p_u = min(1.0, p_hat + 2.576 * sqrt(p_hat * (1 - p_hat) / (L - 1)))
    return -log2(p_u)


def min_entropy_markov(bits: str, seq_len: int = 128) -> float:
    """Markov estimate (SP 800-90B 6.3.3) for a binary source."""
    L = len(bits)
    if L < 2:
        return 0.0
    c = {"00": 0, "01": 0, "10": 0, "11": 0}
    for i in range(L - 1):
        c[bits[i:i + 2]] += 1
    p = [1 - ones_fraction(bits), ones_fraction(bits)]
    n0 = c["00"] + c["01"]
    n1 = c["10"] + c["11"]
    t = [
        [c["00"] / n0 if n0 else 0.0, c["01"] / n0 if n0 else 0.0],
        [c["10"] / n1 if n1 else 0.0, c["11"] / n1 if n1 else 0.0],
    ]
    cur = p[:]
    for _ in range(seq_len - 1):
        cur = [max(cur[s] * t[s][d] for s in (0, 1)) for d in (0, 1)]
    p_max = max(cur)
    if p_max <= 0:
        return 0.0
    return min(-log2(p_max) / seq_len, 1.0)


def serial_correlation(bits: str, lag: int = 1) -> float:
    """Pearson correlation between bit i and bit i+lag."""
    n = len(bits) - lag
    if n < 2:
        return float("nan")
    x = [int(b) for b in bits]
    mx = sum(x) / len(x)
    num = sum((x[i] - mx) * (x[i + lag] - mx) for i in range(n))
    den = sum((v - mx) ** 2 for v in x)
    return num / den if den else float("nan")


def runs_test(bits: str) -> Dict[str, float]:
    """Wald-Wolfowitz runs test z-score and the longest run."""
    n = len(bits)
    n1 = bits.count("1")
    n0 = n - n1
    if n0 == 0 or n1 == 0 or n < 2:
        return {"runs": float(n > 0), "z": float("nan"), "longest_run": float(n)}
    runs = 1 + sum(1 for i in range(1, n) if bits[i] != bits[i - 1])
    mu = 2 * n0 * n1 / n + 1
    var = (mu - 1) * (mu - 2) / (n - 1)
    z = (runs - mu) / sqrt(var) if var > 0 else float("nan")
    longest = cur = 1
    for i in range(1, n):
        cur = cur + 1 if bits[i] == bits[i - 1] else 1
        longest = max(longest, cur)
    return {"runs": float(runs), "z": z, "longest_run": float(longest)}


def per_position_bias(shots: Sequence[str]) -> List[float]:
    """Fraction of ones at each bit position (i.e. per qubit) across shots."""
    if not shots:
        return []
    width = len(shots[0])
    counts = [0] * width
    for s in shots:
        for i, ch in enumerate(s):
            if ch == "1":
                counts[i] += 1
    return [c / len(shots) for c in counts]


def summarise(bits: str, shots: Optional[Sequence[str]] = None) -> Dict:
    """All statistics for one bit string. `shots` enables per-position bias."""
    out: Dict = {
        "bits": len(bits),
        "ones_fraction": ones_fraction(bits),
        "shannon_per_bit": shannon_entropy_per_bit(bits),
        "min_entropy_mcv": min_entropy_mcv(bits),
        "min_entropy_markov": min_entropy_markov(bits),
        "serial_correlation_lag1": serial_correlation(bits, 1),
    }
    out.update({f"runs_{k}": v for k, v in runs_test(bits).items()})
    if shots:
        bias = per_position_bias(shots)
        worst = max(range(len(bias)), key=lambda i: abs(bias[i] - 0.5)) if bias else None
        out["positions"] = len(bias)
        out["per_position_ones"] = bias
        out["worst_position"] = worst
        out["worst_position_ones"] = bias[worst] if worst is not None else None
        out["mean_abs_bias"] = sum(abs(b - 0.5) for b in bias) / len(bias) if bias else None
    return out
