"""Bit streams, unbiased integer sampling, and von Neumann conditioning."""
from __future__ import annotations

from typing import List, Sequence

from .games import bits_for


class BitsExhausted(RuntimeError):
    pass


class BitStream:
    """Consume a string of '0'/'1' characters left to right."""

    def __init__(self, bits: str):
        self.bits = bits
        self.pos = 0
        self.rejections = 0

    @property
    def remaining(self) -> int:
        return len(self.bits) - self.pos

    @property
    def consumed(self) -> int:
        return self.pos

    def take(self, n: int) -> int:
        if n > self.remaining:
            raise BitsExhausted(
                f"needed {n} more bits but only {self.remaining} left; request more shots"
            )
        chunk = self.bits[self.pos:self.pos + n]
        self.pos += n
        return int(chunk, 2) if n else 0

    def uniform_below(self, n: int) -> int:
        """Uniform integer in [0, n) by rejection sampling. No modulo bias."""
        if n == 1:
            return 0
        b = bits_for(n)
        while True:
            x = self.take(b)
            if x < n:
                return x
            self.rejections += 1


def von_neumann_by_position(shots: Sequence[str]) -> str:
    """
    Debias by pairing consecutive shots position-by-position.

    Bits from the same qubit across independent shots share one bias, which is
    exactly the case where von Neumann's trick yields perfectly fair bits.
    Output order: pair-major, then qubit position, so the stream interleaves qubits.
    """
    out: List[str] = []
    for i in range(0, len(shots) - 1, 2):
        a, b = shots[i], shots[i + 1]
        for x, y in zip(a, b):
            if x != y:
                out.append(x)
    return "".join(out)


def concat_shots(shots: Sequence[str]) -> str:
    return "".join(shots)
