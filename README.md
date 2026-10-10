# qdraw

Random draws from measurements on IBM quantum processors, debiased and
audited. Each draw reports how biased the raw bits were, conditions them
before use, decodes them without modulo bias, runs a Bell test in the same
job, and saves a record you can replay. Ships with Australian lottery presets
and takes any "pick k from n" shape.

```
$ qdraw draw --game powerball --games 4

Powerball: 7 from 1-35 + 1 from 1-20   source: ibm_torino

  Game  1:   3  4  7  9 16 22 27  |   6
  Game  2:   2 12 14 17 23 32 33  |  19
  Game  3:   3  4  6 14 22 26 29  |  11
  Game  4:  16 19 21 30 32 33 35  |  10

Entropy report
  raw bits             7,200   (12 qubits x 600 shots)
  ones fraction        0.5075   (ideal 0.5000)
  worst qubit          qubit 11: ones 0.5400, mean |bias| 0.0139
  min-entropy / bit    0.936 (most common value), 0.987 (Markov)
  serial correlation   -0.0093   runs z = 0.77
  conditioned bits     1,822   (von Neumann, 25.3% kept)
  min-entropy / bit    0.905 (most common value), 0.936 (Markov)   after conditioning, n=1,822
  serial correlation   -0.0456   after conditioning
  information / game   27.00 bits   used 132 bits for 4 games (33.0 per game, 4 rejections)

Bell test (CHSH)       S = 2.697 +/- 0.060   classical <= 2, quantum <= 2.828   PASS: device behaved non-classically
Calibration            readout error of chosen qubits: min 0.0051, median 0.0071, max 0.0186
IBM job                d3abc...
Record                 ~/.qdraw/draws/2026-10-10T035458Z_ibm_d3abc....json
```

## What it does differently

Most "quantum random number" demos measure some qubits and print the bits.
That skips three things this project takes seriously.

**The bits coming off real hardware are not perfectly fair.** Readout error on
current IBM chips is around 1 to 3% per qubit and leans toward 0, and
neighbouring qubits nudge each other. qdraw measures this (per-qubit bias,
NIST SP 800-90B min-entropy estimates, serial correlation, runs test) and then
conditions the bits with a von Neumann extractor applied per qubit across
shots, which is the one situation where that extractor is provably exact.

**Turning bits into a ticket must not add bias either.** Taking a 23-bit number
modulo 8,145,060 makes 3% of Saturday Lotto tickets twice as likely as the
rest. qdraw uses rejection sampling and the combinatorial number system, so
every ticket is equally likely and no list of combinations is ever built in
memory. Oz Lotto's 62.9 million combinations cost nothing.

**Check that the machine was behaving quantum mechanically.** Eight qubits
in every job run a CHSH Bell test on four entangled pairs. A result above 2
is inconsistent with any local classical model of those pairs. On shared
cloud hardware this is a sanity check that entanglement was present during
your job, not a loophole-free certificate that the bits are random. The
report says which.

Every draw is saved as a record (game, qubits used, every measured bit, the
games) so anyone with the IBM job id and this code can recompute the same
games with `qdraw audit`. Replay trusts IBM's stored job result; it does
not re-measure anything.

## Install

```bash
git clone https://github.com/ryandau/qdraw.git
cd qdraw
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Then save your IBM Quantum credentials once. Get a token at
[quantum.cloud.ibm.com](https://quantum.cloud.ibm.com); newer accounts also
need the instance CRN from the same page.

```bash
qdraw login --token YOUR_TOKEN [--instance crn:v1:...]
```

`QISKIT_IBM_TOKEN` and `QISKIT_IBM_INSTANCE` environment variables work too.

## Use

```bash
qdraw games                                  # list presets
qdraw draw                                   # Saturday Lotto, 4 games, on real hardware
qdraw draw -g ozlotto -G 12                  # 12 Oz Lotto games
qdraw draw -k 8 -n 50 --supp-pick 2 --supp-pool 12   # any game shape
qdraw draw -s sim                            # ideal local simulator, no account needed
qdraw draw -s os                             # OS CSPRNG, for comparison
qdraw draw --raw                             # skip conditioning and see the difference
qdraw draw --json                            # machine readable
qdraw audit <job_id>                         # re-download a job and recompute the games
qdraw audit --record ~/.qdraw/draws/...   # same, offline from the saved record
```

Presets: `saturday`, `weekday`, `ozlotto`, `powerball`, `setforlife`.

Useful flags for `draw`: `--backend NAME`, `--qubits N` (cap RNG qubits),
`--shots N`, `--no-bell`, `--no-save`, `--quiet`.

### Python

```python
from qdraw.draw import run_draw
from qdraw.games import get_preset

d = run_draw(get_preset("ozlotto"), 6)          # source="ibm" by default; "sim" or "os" also work
for g in d.games:
    print(g.main, g.supp)
print(d.entropy_raw["min_entropy_mcv"], d.bell["S"], d.sample.job_id)
```

The old `QuantumLotteryGenerator` class in `quantum_lottery_generator.py`
still works and now returns the entropy report in its metadata.

## How a draw works

1. Pick qubits. The backend publishes each qubit's readout error. The four
   Bell pairs go on the cleanest coupled pairs, the RNG register on the next
   cleanest qubits. Faulty qubits are skipped.
2. Build one circuit: Hadamard and measure on every RNG qubit; prepare,
   rotate and measure the four Bell pairs. Depth is tiny so decoherence barely
   matters.
3. Run it with enough shots for the games requested (minimum 256). Shots are
   cheap, qubits are not, so bits are never limited by chip size. Twirling
   and dynamical decoupling are turned off so the bits stay raw.
4. Condition. For each qubit, pair up consecutive shots; `01` emits 0, `10`
   emits 1, `00` and `11` are discarded. About a quarter of the raw bits survive
   and they are unbiased regardless of each qubit's individual lean.
5. Decode. Draw a uniform index below C(pool, pick) by rejection sampling,
   unrank it to a sorted ticket. Supplementary barrels (Powerball) are drawn
   the same way from their own bits.
6. Report and record.

## Reading the entropy report

- **ones fraction / worst qubit**: raw bias. Hardware typically shows 0.48 to
  0.50 overall with the odd qubit at 0.45. The ideal simulator and the OS
  source hover at 0.50.
- **min-entropy / bit**: how unpredictable each bit is, per NIST SP 800-90B.
  1.0 is perfect. The most-common-value figure is a 99% confidence bound so it
  is pessimistic on small samples; compare runs of similar size or look at the
  Markov figure. Bits per game in the last line tells you how many bits of
  this quality each ticket consumed.
- **serial correlation / runs z**: should be near 0 and within about +/-2.
- **Bell S**: above 2 by several standard errors means the entangled pairs
  showed non-classical correlations during this job. Noisy hardware gives
  roughly 2.5 to 2.75; the ideal simulator approaches 2.83. Below 2 means the
  pairs decohered or the calibration was off, and you should treat the RNG
  bits from that job with more suspicion, not less.

An honest finding you will see: raw hardware bits score lower than the OS
CSPRNG until they are conditioned. The measurement outcome is physically
unpredictable; the readout electronics add a tilt on top. Conditioning
removes the tilt, which is why it is on by default. None of this makes the
numbers more likely to win.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests cover unranking against brute force, modulo-bias-free sampling, the
extractor, the estimators, CHSH arithmetic, record replay, and a full run of
the hardware code path on `FakeTorino` with real calibration data.

## Disclaimer

For education and curiosity. Given conditioned bits, every ticket is equally
likely; that is all this guarantees. Lottery draws are independent random
events and nothing here changes your odds.

## License

MIT
