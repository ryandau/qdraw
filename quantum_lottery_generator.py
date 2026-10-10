"""
Backwards-compatible entry point. The implementation now lives in the `qdraw` package.

    python quantum_lottery_generator.py            ->  qdraw draw
    QuantumLotteryGenerator(6, 45, 4).generate()   ->  still works
"""
from __future__ import annotations

import sys
from typing import Optional

from qdraw.cli import main as _cli_main
from qdraw.draw import run_draw
from qdraw.games import custom_spec


class QuantumLotteryGenerator:
    def __init__(self, numbers_per_game: int = 6, number_range: int = 45, num_games: int = 4):
        self.spec = custom_spec(numbers_per_game, number_range)
        self.num_games = num_games

    def generate(self, token: Optional[str] = None, backend_name: Optional[str] = None,
                 instance: Optional[str] = None, source: str = "ibm") -> dict:
        d = run_draw(self.spec, self.num_games, source=source, backend_name=backend_name,
                     token=token, instance=instance)
        return {
            "games": [g.main for g in d.games],
            "quantum_state": "".join(d.sample.rng_shots),
            "backend": d.sample.backend,
            "metadata": {
                "num_qubits": d.sample.width,
                "shots": d.sample.shots,
                "job_id": d.sample.job_id,
                "conditioning": d.conditioning,
                "entropy": d.entropy_raw,
                "bell": d.bell,
                "record": d.record_path,
            },
        }


if __name__ == "__main__":
    sys.exit(_cli_main(["draw"] + sys.argv[1:]))
