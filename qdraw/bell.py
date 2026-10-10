"""
CHSH Bell test: a quantumness witness run alongside the number generation.

Four entangled pairs, one per measurement setting. Alice measures along angle
a in {0, pi/2}, Bob along b in {pi/4, -pi/4} (X-Z plane). For a perfect Bell
state S = 2*sqrt(2) ~ 2.83. Any local classical model gives S <= 2.
"""
from __future__ import annotations

from math import pi, sqrt
from typing import Dict, List, Sequence

SETTINGS = [(0.0, pi / 4), (0.0, -pi / 4), (pi / 2, pi / 4), (pi / 2, -pi / 4)]
SIGNS = [1, 1, 1, -1]
N_BELL_QUBITS = 2 * len(SETTINGS)
CLASSICAL_BOUND = 2.0
QUANTUM_BOUND = 2 * sqrt(2)


def add_bell_pairs(qc, qubits: Sequence[int], clbits: Sequence[int]) -> None:
    """Append the four CHSH pairs to circuit `qc` on the given 8 qubits/clbits."""
    assert len(qubits) == N_BELL_QUBITS and len(clbits) == N_BELL_QUBITS
    for s, (alpha, beta) in enumerate(SETTINGS):
        qa, qb = qubits[2 * s], qubits[2 * s + 1]
        qc.h(qa)
        qc.cx(qa, qb)
        if alpha:
            qc.ry(-alpha, qa)
        qc.ry(-beta, qb)
        qc.measure(qa, clbits[2 * s])
        qc.measure(qb, clbits[2 * s + 1])


def chsh(bell_shots: Sequence[str]) -> Dict:
    """
    Compute S from per-shot 8-bit strings ordered as clbit 0..7
    (pair s occupies positions 2s, 2s+1).
    """
    n = len(bell_shots)
    if n == 0:
        return {"available": False}
    E: List[float] = []
    var: List[float] = []
    for s in range(len(SETTINGS)):
        same = sum(1 for sh in bell_shots if sh[2 * s] == sh[2 * s + 1])
        e = (2 * same - n) / n
        E.append(e)
        var.append((1 - e * e) / n)
    S = sum(sg * e for sg, e in zip(SIGNS, E))
    err = sqrt(sum(var))
    return {
        "available": True,
        "shots": n,
        "E": E,
        "S": S,
        "S_err": err,
        "classical_bound": CLASSICAL_BOUND,
        "quantum_bound": QUANTUM_BOUND,
        "violates_classical": S - 3 * err > CLASSICAL_BOUND,
        "sigmas_above_classical": (S - CLASSICAL_BOUND) / err if err else float("inf"),
    }
