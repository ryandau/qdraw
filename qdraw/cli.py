"""Command line interface: qdraw draw | audit | games."""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from typing import Dict, Optional

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

from . import __version__
from .draw import Draw, find_record, load_record, record_dict, replay, run_draw
from .games import PRESETS, GameSpec, custom_spec, get_preset
from .sources import fetch_ibm_job


def _spec_from_args(a) -> GameSpec:
    if a.game:
        return get_preset(a.game)
    if a.pick and a.pool:
        return custom_spec(a.pick, a.pool, a.supp_pick or 0, a.supp_pool or 0)
    return get_preset("saturday")


def _f(x: Optional[float], nd: int = 3) -> str:
    return "n/a" if x is None or x != x else f"{x:.{nd}f}"


def print_draw(d: Draw, verbose: bool = False) -> None:
    spec, s, er, ec, b = d.spec, d.sample, d.entropy_raw, d.entropy_conditioned, d.bell
    print(f"{spec.label}: {spec.describe()}   source: {s.backend}")
    print()
    for i, g in enumerate(d.games, 1):
        print(f"  Game {i:>2}:  {g}")
    print()

    worst = ""
    if er.get("worst_position") is not None and s.layout.get("rng"):
        worst = f", worst qubit {s.layout['rng'][er['worst_position']]} at {_f(er['worst_position_ones'])}"
    print(f"  raw bits        {d.raw_bits:,} from {s.width} qubits x {s.shots} shots, "
          f"ones {_f(er['ones_fraction'])}{worst}")
    print(f"  min-entropy     {_f(er['min_entropy_mcv'])} per raw bit (1.000 is perfect)")
    if ec:
        print(f"  conditioned     {d.conditioned_bits:,} bits kept ({100 * d.conditioned_bits / max(d.raw_bits, 1):.0f}%), "
              f"ones {_f(ec['ones_fraction'])}, {d.bits_used:,} used for {len(d.games)} games")
    if b.get("available"):
        verdict = "non-classical" if b["violates_classical"] else "NO VIOLATION, treat this job with suspicion"
        print(f"  Bell test       S = {b['S']:.2f} +/- {b['S_err']:.2f}  (classical <= 2, quantum <= 2.83)  {verdict}")
    else:
        print("  Bell test       not run")

    if verbose:
        print()
        print("Detail")
        print(f"  shannon entropy / raw bit     {_f(er['shannon_per_bit'], 4)}")
        print(f"  min-entropy MCV, conditioned  {_f(ec['min_entropy_mcv']) if ec else 'n/a'}"
              + (f"   (99% bound on n={d.conditioned_bits:,}; tightens with more shots)" if ec else ""))
        print(f"  min-entropy Markov, raw       {_f(er['min_entropy_markov'])}"
              + (f"   conditioned {_f(ec['min_entropy_markov'])}" if ec else ""))
        print(f"  serial correlation, raw       {_f(er['serial_correlation_lag1'], 4)}"
              + (f"   conditioned {_f(ec['serial_correlation_lag1'], 4)}" if ec else ""))
        print(f"  runs test z, raw              {_f(er['runs_z'], 2)}   longest run {int(er['runs_longest_run'])}")
        print(f"  mean |bias| per qubit         {_f(er.get('mean_abs_bias'), 4)}")
        print(f"  information per game          {spec.entropy_bits:.2f} bits, "
              f"{d.bits_per_game_used:.1f} consumed, {d.rejections} rejections")
        if b.get("available"):
            print(f"  CHSH correlators              " + ", ".join(f"{e:+.3f}" for e in b["E"])
                  + f"   ({b['sigmas_above_classical']:.1f} sigma above 2)")
        vals = [v for v in s.readout_errors.values() if v is not None]
        if vals:
            vals.sort()
            print(f"  readout error, chosen qubits  min {vals[0]:.4f}  median {vals[len(vals)//2]:.4f}  max {vals[-1]:.4f}")
        if s.layout.get("rng"):
            print(f"  RNG qubits                    {s.layout['rng']}")
            print(f"  Bell qubits                   {s.layout.get('bell')}")
    print()
    if s.job_id:
        print(f"  job      {s.job_id}")
    if d.record_path:
        print(f"  record   {d.record_path}")


def cmd_draw(a) -> int:
    spec = _spec_from_args(a)
    log = (lambda m: None) if a.json else (lambda m: print(m, file=sys.stderr))
    d = run_draw(spec, a.games, source=a.source, backend_name=a.backend, shots=a.shots,
                 save=not a.no_save, log=log)
    if a.json:
        rec = record_dict(d)
        rec.pop("rng_shots", None)
        rec.pop("bell_shots", None)
        rec["entropy_raw"].pop("per_position_ones", None)
        rec["record_path"] = d.record_path
        print(json.dumps(rec, indent=1))
    else:
        print_draw(d, verbose=a.verbose)
    return 0


def cmd_audit(a) -> int:
    record: Optional[Dict] = None
    path = a.record or (find_record(a.job_id) if a.job_id else None)
    if path:
        record = load_record(path)
        print(f"record: {path}", file=sys.stderr)
    if a.job_id:
        sample = fetch_ibm_job(a.job_id)
        if record is None:
            print("no local record for this job; decoding with the game given on the command line", file=sys.stderr)
            record = {"game": _spec_from_args(a).to_dict(), "games_requested": a.games, "conditioning": "von_neumann"}
        d = replay(record, sample)
    elif record is not None:
        d = replay(record)
    else:
        print("audit needs a job id or --record PATH", file=sys.stderr)
        return 2

    print_draw(d, verbose=a.verbose)
    if record.get("games"):
        same = [(g["main"], g.get("supp", [])) for g in record["games"]] == [(g.main, g.supp) for g in d.games]
        print("  verify   " + ("games recomputed from the measurements match the record" if same
                              else "MISMATCH: recomputed games differ from the record"))
        return 0 if same else 1
    return 0


def cmd_games(a) -> int:
    print(f"{'name':<12}{'label':<18}{'draw':<26}{'combinations':>16}{'bits/game':>11}")
    for name, s in PRESETS.items():
        print(f"{name:<12}{s.label:<18}{s.describe():<26}{s.combinations * s.supp_combinations:>16,}"
              f"{s.entropy_bits:>11.2f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qdraw",
                                description="Random draws from IBM quantum processor measurements, debiased and audited.")
    p.add_argument("--version", action="version", version=f"qdraw {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def game_args(sp):
        g = sp.add_argument_group("game")
        g.add_argument("--game", "-g", help=f"preset: {', '.join(PRESETS)} (default saturday)")
        g.add_argument("--games", "-G", type=int, default=4, help="how many games (default 4)")
        g.add_argument("--pick", "-k", type=int, help="custom game: numbers per game")
        g.add_argument("--pool", "-n", type=int, help="custom game: drawn from 1..POOL")
        g.add_argument("--supp-pick", type=int, default=0, help="custom game: extra numbers from a second barrel")
        g.add_argument("--supp-pool", type=int, default=0, help="custom game: second barrel is 1..SUPP_POOL")

    d = sub.add_parser("draw", help="generate games")
    game_args(d)
    d.add_argument("--source", "-s", choices=["ibm", "sim"], default="ibm",
                   help="ibm hardware (default) or a local ideal simulator")
    d.add_argument("--backend", help="IBM backend name (default: least busy)")
    d.add_argument("--shots", type=int, help="measurement shots (default: enough for the games, min 256)")
    d.add_argument("--verbose", "-v", action="store_true", help="full statistics")
    d.add_argument("--json", action="store_true", help="machine-readable output")
    d.add_argument("--no-save", action="store_true", help="do not write a record file")
    d.set_defaults(func=cmd_draw)

    au = sub.add_parser("audit", help="recompute a past draw and check it against its record")
    au.add_argument("job_id", nargs="?", help="IBM job id to re-download")
    au.add_argument("--record", help="record file to replay offline")
    au.add_argument("--verbose", "-v", action="store_true", help="full statistics")
    game_args(au)
    au.set_defaults(func=cmd_audit)

    gm = sub.add_parser("games", help="list game presets")
    gm.set_defaults(func=cmd_games)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ncancelled", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        msg = str(e).lower()
        if "instance" in msg or "credential" in msg or "token" in msg or "unable to retrieve" in msg:
            print("hint: see README 'IBM Quantum setup' for saving your API key and instance", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
