"""Turn a Sample into lottery games, plus the entropy report and a saved record."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import __version__
from .bell import chsh
from .bits import BitStream, BitsExhausted, concat_shots, von_neumann_by_position
from .combinatorics import unrank_combination
from .entropy import summarise
from .games import GameSpec, raw_bits_needed
from .sources import Sample, sample_ibm, sample_os, sample_sim

RECORD_DIR = os.environ.get("QDRAW_HOME") or os.path.join(os.path.expanduser("~"), ".qdraw", "draws")
MIN_SHOTS = 256


@dataclass
class Game:
    main: List[int]
    supp: List[int] = field(default_factory=list)

    def __str__(self) -> str:
        s = " ".join(f"{n:2d}" for n in self.main)
        if self.supp:
            s += "  |  " + " ".join(f"{n:2d}" for n in self.supp)
        return s


@dataclass
class Draw:
    spec: GameSpec
    games: List[Game]
    sample: Sample
    conditioning: str
    raw_bits: int
    conditioned_bits: int
    bits_used: int
    rejections: int
    entropy_raw: Dict
    entropy_conditioned: Optional[Dict]
    bell: Dict
    created: str = ""
    record_path: Optional[str] = None

    @property
    def bits_per_game_used(self) -> float:
        return self.bits_used / len(self.games) if self.games else 0.0


def decode(spec: GameSpec, n_games: int, rng_shots: List[str], conditioning: str) -> Dict:
    """Pure function: bits in, games out. Used by both `draw` and `audit`."""
    raw = concat_shots(rng_shots)
    if conditioning == "von_neumann":
        stream_bits = von_neumann_by_position(rng_shots)
    elif conditioning == "none":
        stream_bits = raw
    else:
        raise ValueError(f"unknown conditioning '{conditioning}'")

    stream = BitStream(stream_bits)
    games: List[Game] = []
    for _ in range(n_games):
        idx = stream.uniform_below(spec.combinations)
        main = unrank_combination(idx, spec.pool, spec.pick)
        supp: List[int] = []
        if spec.supp_pick:
            sidx = stream.uniform_below(spec.supp_combinations)
            supp = unrank_combination(sidx, spec.supp_pool, spec.supp_pick)
        games.append(Game(main, supp))

    return {
        "games": games,
        "raw_bits": len(raw),
        "conditioned_bits": len(stream_bits),
        "bits_used": stream.consumed,
        "rejections": stream.rejections,
        "raw": raw,
        "stream": stream_bits,
    }


def run_draw(
    spec: GameSpec,
    n_games: int,
    source: str = "ibm",
    conditioning: str = "von_neumann",
    bell: bool = True,
    backend_name: Optional[str] = None,
    n_qubits: Optional[int] = None,
    shots: Optional[int] = None,
    token: Optional[str] = None,
    instance: Optional[str] = None,
    save: bool = True,
    log=print,
) -> Draw:
    raw_needed = raw_bits_needed(spec, n_games, conditioned=(conditioning == "von_neumann"))
    if source == "ibm":
        sample = sample_ibm(raw_needed, bell=bell, backend_name=backend_name, n_qubits=n_qubits,
                            shots=shots, min_shots=MIN_SHOTS, token=token, instance=instance, log=log)
    elif source == "sim":
        sample = sample_sim(raw_needed, bell=bell, shots=shots, min_shots=MIN_SHOTS)
    elif source == "os":
        sample = sample_os(raw_needed, shots=shots, min_shots=MIN_SHOTS)
    else:
        raise ValueError(f"unknown source '{source}'")
    draw = build_draw(spec, n_games, sample, conditioning)
    if save:
        draw.record_path = save_record(draw)
    return draw


def build_draw(spec: GameSpec, n_games: int, sample: Sample, conditioning: str) -> Draw:
    d = decode(spec, n_games, sample.rng_shots, conditioning)
    ent_raw = summarise(d["raw"], sample.rng_shots)
    ent_cond = summarise(d["stream"]) if conditioning != "none" else None
    bell_res = chsh(sample.bell_shots) if sample.bell_shots else {"available": False}
    return Draw(
        spec=spec, games=d["games"], sample=sample, conditioning=conditioning,
        raw_bits=d["raw_bits"], conditioned_bits=d["conditioned_bits"],
        bits_used=d["bits_used"], rejections=d["rejections"],
        entropy_raw=ent_raw, entropy_conditioned=ent_cond, bell=bell_res,
        created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def record_dict(draw: Draw) -> Dict:
    s = draw.sample
    return {
        "qdraw_version": __version__,
        "created": draw.created,
        "game": draw.spec.to_dict(),
        "games_requested": len(draw.games),
        "conditioning": draw.conditioning,
        "source": s.source,
        "backend": s.backend,
        "job_id": s.job_id,
        "layout": s.layout,
        "readout_errors": {str(k): v for k, v in s.readout_errors.items()},
        "shots": s.shots,
        "width": s.width,
        "rng_shots": s.rng_shots,
        "bell_shots": s.bell_shots,
        "games": [asdict(g) for g in draw.games],
        "bits": {
            "raw": draw.raw_bits, "conditioned": draw.conditioned_bits,
            "used": draw.bits_used, "rejections": draw.rejections,
        },
        "entropy_raw": draw.entropy_raw,
        "entropy_conditioned": draw.entropy_conditioned,
        "bell": draw.bell,
    }


def save_record(draw: Draw, directory: str = RECORD_DIR) -> str:
    os.makedirs(directory, exist_ok=True)
    stamp = draw.created.replace(":", "").replace("+0000", "Z")
    name = f"{stamp}_{draw.sample.source}_{draw.sample.job_id or 'local'}.json"
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        json.dump(record_dict(draw), f, indent=1)
    return path


def load_record(path: str) -> Dict:
    with open(path) as f:
        return json.load(f)


def find_record(job_id: str, directory: str = RECORD_DIR) -> Optional[str]:
    if not os.path.isdir(directory):
        return None
    for name in sorted(os.listdir(directory), reverse=True):
        if name.endswith(f"_{job_id}.json"):
            return os.path.join(directory, name)
    return None


def replay(record: Dict, sample: Optional[Sample] = None) -> Draw:
    """Recompute a draw from a record (offline) or from freshly fetched measurements."""
    spec = GameSpec.from_dict(record["game"])
    if sample is None:
        sample = Sample(
            record["source"], record["rng_shots"], record.get("bell_shots"),
            record["backend"], record.get("job_id"), record.get("layout", {}),
            {int(k): v for k, v in record.get("readout_errors", {}).items()},
        )
    return build_draw(spec, record["games_requested"], sample, record["conditioning"])
