"""Lottery game definitions and bit budgeting."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import comb, ceil, log2
from typing import Dict, Optional


def bits_for(n: int) -> int:
    """Smallest number of bits that can hold a value in [0, n)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    return max(1, (n - 1).bit_length())


@dataclass(frozen=True)
class GameSpec:
    name: str
    pick: int          # numbers chosen per game
    pool: int          # numbers drawn from 1..pool
    supp_pick: int = 0 # extra numbers from a separate barrel (e.g. Powerball)
    supp_pool: int = 0
    label: str = ""

    def __post_init__(self) -> None:
        if not 1 <= self.pick <= self.pool:
            raise ValueError(f"pick must be between 1 and pool (got {self.pick} from {self.pool})")
        if self.supp_pick and not 1 <= self.supp_pick <= self.supp_pool:
            raise ValueError("supp_pick must be between 1 and supp_pool")

    @property
    def combinations(self) -> int:
        return comb(self.pool, self.pick)

    @property
    def supp_combinations(self) -> int:
        return comb(self.supp_pool, self.supp_pick) if self.supp_pick else 1

    @property
    def main_bits(self) -> int:
        return bits_for(self.combinations)

    @property
    def supp_bits(self) -> int:
        return bits_for(self.supp_combinations) if self.supp_pick else 0

    @property
    def entropy_bits(self) -> float:
        """True information content of one game, in bits."""
        return log2(self.combinations) + (log2(self.supp_combinations) if self.supp_pick else 0.0)

    @property
    def expected_bits_per_game(self) -> float:
        """Expected bits consumed per game with rejection sampling."""
        main = self.main_bits * (2 ** self.main_bits) / self.combinations
        supp = 0.0
        if self.supp_pick:
            supp = self.supp_bits * (2 ** self.supp_bits) / self.supp_combinations
        return main + supp

    def describe(self) -> str:
        s = f"{self.pick} from 1-{self.pool}"
        if self.supp_pick:
            s += f" + {self.supp_pick} from 1-{self.supp_pool}"
        return s

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "GameSpec":
        return cls(**d)


PRESETS: Dict[str, GameSpec] = {
    "saturday":   GameSpec("saturday", 6, 45, label="Saturday Lotto"),
    "weekday":    GameSpec("weekday", 6, 45, label="Weekday Windfall"),
    "ozlotto":    GameSpec("ozlotto", 7, 47, label="Oz Lotto"),
    "powerball":  GameSpec("powerball", 7, 35, 1, 20, label="Powerball"),
    "setforlife": GameSpec("setforlife", 7, 44, label="Set for Life"),
}
PRESET_ALIASES = {"lotto": "saturday", "monday": "weekday", "wednesday": "weekday", "sfl": "setforlife"}


def get_preset(name: str) -> GameSpec:
    key = PRESET_ALIASES.get(name.lower(), name.lower())
    if key not in PRESETS:
        raise KeyError(f"unknown game '{name}'. Known: {', '.join(PRESETS)}")
    return PRESETS[key]


def custom_spec(pick: int, pool: int, supp_pick: int = 0, supp_pool: int = 0) -> GameSpec:
    return GameSpec("custom", pick, pool, supp_pick, supp_pool, label="Custom")


def raw_bits_needed(spec: GameSpec, games: int, conditioned: bool, margin: float = 1.5) -> int:
    """Raw measurement bits to request so that decoding is very unlikely to run dry."""
    need = spec.expected_bits_per_game * games * margin + 64
    if conditioned:
        need *= 4.4  # von Neumann keeps ~1/4 of fair bits; a little extra for bias
    return int(ceil(need))
