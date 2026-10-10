"""Command line interface: qdraw draw | audit | games | login."""
from __future__ import annotations

import argparse
import json
import sys
import warnings

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
from typing import Dict, Optional

from . import __version__
from .draw import Draw, find_record, load_record, record_dict, replay, run_draw
from .games import PRESETS, GameSpec, custom_spec, get_preset
from .sources import fetch_ibm_job, save_account


def _spec_from_args(a) -> GameSpec:
    if a.game:
        return get_preset(a.game)
    if a.pick and a.pool:
        return custom_spec(a.pick, a.pool, a.supp_pick or 0, a.supp_pool or 0)
    return get_preset("saturday")


def _fmt(x: Optional[float], nd: int = 4) -> str:
    return "n/a" if x is None or x != x else f"{x:.{nd}f}"


def print_draw(d: Draw, verbose: bool = True) -> None:
    spec, s = d.spec, d.sample
    print(f"{spec.label}: {spec.describe()}   source: {s.backend}")
    print()
    for i, g in enumerate(d.games, 1):
        print(f"  Game {i:>2}:  {g}")
    print()
    if not verbose:
        return
    print("Entropy report")
    print(f"  raw bits             {d.raw_bits:,}   ({s.width} qubits x {s.shots} shots)")
    er = d.entropy_raw
    print(f"  ones fraction        {_fmt(er['ones_fraction'])}   (ideal 0.5000)")
    if er.get("worst_position") is not None:
        q = er["worst_position"]
        phys = s.layout.get("rng", [None] * (q + 1))[q] if s.layout.get("rng") else None
        where = f"qubit {phys}" if phys is not None else f"position {q}"
        print(f"  worst qubit          {where}: ones {_fmt(er['worst_position_ones'])}, "
              f"mean |bias| {_fmt(er['mean_abs_bias'])}")
    print(f"  min-entropy / bit    {_fmt(er['min_entropy_mcv'], 3)} (most common value), "
          f"{_fmt(er['min_entropy_markov'], 3)} (Markov)")
    print(f"  serial correlation   {_fmt(er['serial_correlation_lag1'])}   runs z = {_fmt(er['runs_z'], 2)}")
    if d.entropy_conditioned:
        ec = d.entropy_conditioned
        print(f"  conditioned bits     {d.conditioned_bits:,}   (von Neumann, "
              f"{100 * d.conditioned_bits / max(d.raw_bits, 1):.1f}% kept)")
        print(f"  min-entropy / bit    {_fmt(ec['min_entropy_mcv'], 3)} (most common value), "
              f"{_fmt(ec['min_entropy_markov'], 3)} (Markov)   after conditioning, n={d.conditioned_bits:,}")
        print(f"  serial correlation   {_fmt(ec['serial_correlation_lag1'])}   after conditioning")
    else:
        print("  conditioning         none (raw bits used directly)")
    print(f"  information / game   {spec.entropy_bits:.2f} bits   "
          f"used {d.bits_used:,} bits for {len(d.games)} games "
          f"({d.bits_per_game_used:.1f} per game, {d.rejections} rejections)")
    print()
    b = d.bell
    if b.get("available"):
        verdict = "PASS: pairs showed non-classical correlations" if b["violates_classical"] else "FAIL: no violation; treat this job's bits with suspicion"
        print(f"Bell test (CHSH)       S = {b['S']:.3f} +/- {b['S_err']:.3f}   "
              f"classical <= 2, quantum <= {b['quantum_bound']:.3f}   {verdict}")
    else:
        print("Bell test (CHSH)       not run")
    if s.readout_errors:
        vals = [v for v in s.readout_errors.values() if v is not None]
        if vals:
            print(f"Calibration            readout error of chosen qubits: "
                  f"min {min(vals):.4f}, median {sorted(vals)[len(vals)//2]:.4f}, max {max(vals):.4f}")
    if s.job_id:
        print(f"IBM job                {s.job_id}")
    if d.record_path:
        print(f"Record                 {d.record_path}")


def cmd_draw(a) -> int:
    spec = _spec_from_args(a)
    conditioning = "none" if a.raw else "von_neumann"
    log = (lambda *x, **k: None) if a.json else (lambda m: print(m, file=sys.stderr))
    d = run_draw(
        spec, a.games, source=a.source, conditioning=conditioning, bell=not a.no_bell,
        backend_name=a.backend, n_qubits=a.qubits, shots=a.shots,
        token=a.token, instance=a.instance, save=not a.no_save, log=log,
    )
    if a.json:
        rec = record_dict(d)
        if not a.full:
            rec.pop("rng_shots", None)
            rec.pop("bell_shots", None)
            rec["entropy_raw"].pop("per_position_ones", None)
        rec["record_path"] = d.record_path
        print(json.dumps(rec, indent=1))
    else:
        print_draw(d, verbose=not a.quiet)
    return 0


def cmd_audit(a) -> int:
    record: Optional[Dict] = None
    path = a.record or (find_record(a.job_id) if a.job_id else None)
    if path:
        record = load_record(path)
        print(f"record: {path}", file=sys.stderr)
    if a.job_id:
        sample = fetch_ibm_job(a.job_id, a.token, a.instance)
        if record is None:
            spec = _spec_from_args(a)
            record = {"game": spec.to_dict(), "games_requested": a.games,
                      "conditioning": "none" if a.raw else "von_neumann"}
            print("no local record found; decoding with the game settings given on the command line",
                  file=sys.stderr)
        d = replay(record, sample)
    elif record is not None:
        d = replay(record)
    else:
        print("audit needs a job id or --record PATH", file=sys.stderr)
        return 2

    print_draw(d)
    if record.get("games"):
        same = [g["main"] for g in record["games"]] == [g.main for g in d.games] and \
               [g.get("supp", []) for g in record["games"]] == [g.supp for g in d.games]
        print()
        print("Verification           " + ("games recomputed from the measurements MATCH the record"
                                            if same else "MISMATCH: recomputed games differ from the record"))
        return 0 if same else 1
    return 0


def cmd_games(a) -> int:
    print(f"{'name':<12}{'label':<18}{'draw':<26}{'combinations':>16}{'bits/game':>11}")
    for name, s in PRESETS.items():
        combos = s.combinations * s.supp_combinations
        print(f"{name:<12}{s.label:<18}{s.describe():<26}{combos:>16,}{s.entropy_bits:>11.2f}")
    return 0


def cmd_login(a) -> int:
    save_account(a.token, a.instance)
    print("saved IBM Quantum credentials for future runs")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qdraw", description="Random draws from IBM quantum processor measurements, debiased and audited.")
    p.add_argument("--version", action="version", version=f"qdraw {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def game_args(sp):
        g = sp.add_argument_group("game")
        g.add_argument("--game", "-g", help=f"preset: {', '.join(PRESETS)} (default saturday)")
        g.add_argument("--pick", "-k", type=int, help="numbers per game (custom game)")
        g.add_argument("--pool", "-n", dest="pool", type=int, help="draw from 1..POOL (custom game)")
        g.add_argument("--supp-pick", type=int, default=0, help="extra numbers from a second barrel")
        g.add_argument("--supp-pool", type=int, default=0, help="second barrel is 1..SUPP_POOL")
        g.add_argument("--games", "-G", type=int, default=4, help="how many games (default 4)")
        g.add_argument("--raw", action="store_true", help="skip von Neumann conditioning")

    def ibm_args(sp):
        i = sp.add_argument_group("ibm")
        i.add_argument("--token", help="IBM Quantum API token (or QISKIT_IBM_TOKEN, or saved account)")
        i.add_argument("--instance", help="IBM Quantum instance CRN (or QISKIT_IBM_INSTANCE)")

    d = sub.add_parser("draw", help="generate games")
    game_args(d)
    d.add_argument("--source", "-s", choices=["ibm", "sim", "os"], default="ibm",
                   help="ibm hardware (default), local ideal simulator, or OS CSPRNG")
    d.add_argument("--backend", help="specific IBM backend name (default: least busy)")
    d.add_argument("--qubits", type=int, help="max RNG qubits to use (default: all good ones)")
    d.add_argument("--shots", type=int, help="shots (default: enough for the games, min 256)")
    d.add_argument("--no-bell", action="store_true", help="skip the CHSH Bell test")
    d.add_argument("--no-save", action="store_true", help="do not write a record file")
    d.add_argument("--quiet", "-q", action="store_true", help="games only, no report")
    d.add_argument("--json", action="store_true", help="machine-readable output")
    d.add_argument("--full", action="store_true", help="with --json, include every measured bit")
    ibm_args(d)
    d.set_defaults(func=cmd_draw)

    au = sub.add_parser("audit", help="recompute a past draw and print its entropy report")
    au.add_argument("job_id", nargs="?", help="IBM job id to re-download")
    au.add_argument("--record", help="local record file to replay offline")
    game_args(au)
    ibm_args(au)
    au.set_defaults(func=cmd_audit)

    gm = sub.add_parser("games", help="list game presets")
    gm.set_defaults(func=cmd_games)

    lg = sub.add_parser("login", help="save IBM Quantum credentials")
    lg.add_argument("--token", required=True)
    lg.add_argument("--instance")
    lg.set_defaults(func=cmd_login)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ncancelled", file=sys.stderr)
        return 130
    except Exception as e:  # keep the CLI readable
        print(f"error: {e}", file=sys.stderr)
        if "instance" in str(e).lower():
            print("hint: your IBM account may need an instance CRN. Find it at https://quantum.cloud.ibm.com "
                  "and pass --instance or run `qdraw login --token ... --instance ...`", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
