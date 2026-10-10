"""Rank/unrank k-subsets without materialising the whole list."""
from __future__ import annotations

from math import comb
from typing import List, Sequence


def unrank_combination(rank: int, n: int, k: int) -> List[int]:
    """Return the `rank`-th k-subset of {1..n} in lexicographic order (0-based)."""
    total = comb(n, k)
    if not 0 <= rank < total:
        raise ValueError(f"rank {rank} out of range [0, {total})")
    out: List[int] = []
    v = 1
    remaining = k
    while remaining > 0:
        c = comb(n - v, remaining - 1)
        if rank < c:
            out.append(v)
            remaining -= 1
        else:
            rank -= c
        v += 1
    return out


def rank_combination(combo: Sequence[int], n: int) -> int:
    """Inverse of unrank_combination. `combo` must be strictly increasing values in 1..n."""
    k = len(combo)
    rank = 0
    prev = 0
    for i, c in enumerate(combo):
        if not prev < c <= n:
            raise ValueError("combo must be strictly increasing within 1..n")
        remaining = k - i
        for v in range(prev + 1, c):
            rank += comb(n - v, remaining - 1)
        prev = c
    return rank
