# qdraw

Random draws from measurements on IBM quantum processors, debiased and audited.
Comes with Australian lottery presets and takes any "pick k from n" shape.

```
$ qdraw draw --game ozlotto --games 3

Oz Lotto: 7 from 1-47   source: ibm_torino

  Game  1:   1  3  6  9 32 36 43
  Game  2:   6 10 13 16 26 33 38
  Game  3:   2 10 16 18 21 28 42

  raw bits        31,744 from 124 qubits x 256 shots, ones 0.489, worst qubit 87 at 0.441
  min-entropy     0.934 per raw bit (1.000 is perfect)
  conditioned     7,802 bits kept (25%), ones 0.501, 84 used for 3 games
  Bell test       S = 2.64 +/- 0.03  (classical <= 2, quantum <= 2.83)  non-classical

  job      d3k9...
  record   ~/.qdraw/draws/2026-10-10T051203Z_ibm_d3k9....json
```

*(Illustrative output. Replace with a real run once you have an account.)*

## Why

Measuring a qubit in superposition gives a physically unpredictable bit, but the
bits that come off real hardware are not perfectly fair: readout error tilts them
a few percent toward 0. Most quantum-random demos ignore that. qdraw measures the
tilt, removes it with a von Neumann extractor, turns the clean bits into tickets
without the usual modulo bias, and runs a Bell test in the same job so you can
see the device was behaving quantum mechanically when your numbers were drawn.
Every draw is saved so it can be recomputed later from IBM's record of the job.

Details and how to read the numbers: [docs/how-it-works.md](docs/how-it-works.md).

## Install

```bash
git clone https://github.com/ryandau/qdraw.git
cd qdraw
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## IBM Quantum setup

The free Open plan gives 10 minutes of processor time per 28 days, which is
hundreds of draws.

1. Create an IBM Cloud account at <https://quantum.cloud.ibm.com/registration>.
2. On the [IBM Quantum Platform](https://quantum.cloud.ibm.com) dashboard, create
   an instance on the Open plan, then create an API key. Copy the key when it is
   shown; it is only shown once.
3. Save the credentials for Qiskit (one time):

   ```python
   from qiskit_ibm_runtime import QiskitRuntimeService
   QiskitRuntimeService.save_account(channel="ibm_quantum_platform", token="YOUR_API_KEY")
   ```

   If you have more than one instance, add `instance="crn:v1:..."` (copy the CRN
   from the Instances page). `QISKIT_IBM_TOKEN` and `QISKIT_IBM_INSTANCE`
   environment variables also work.

No account? `qdraw draw --source sim` runs everything on a local noiseless
simulator.

## Use

```bash
qdraw games                               # list presets
qdraw draw                                # Saturday Lotto, 4 games, real hardware
qdraw draw -g powerball -G 10             # 10 Powerball games
qdraw draw -k 8 -n 50 --supp-pick 2 --supp-pool 12    # any game shape
qdraw draw -v                             # full statistics
qdraw audit <job_id>                      # re-download a job and recompute its games
```

Presets: `saturday`, `weekday`, `ozlotto`, `powerball`, `setforlife`.
Other flags: `--backend NAME`, `--shots N`, `--json`, `--no-save`.

## How it works

1. Pick the qubits with the lowest readout error; put four Bell pairs on the
   cleanest coupled pairs.
2. One shallow circuit: Hadamard and measure on the RNG qubits, prepare and
   measure the Bell pairs. Run it for enough shots, minimum 256.
3. Condition: for each qubit, pair consecutive shots; `01` emits 0, `10` emits 1,
   the rest are dropped. The survivors are unbiased.
4. Decode: a uniform index below C(pool, pick) by rejection sampling, unranked
   straight to a sorted ticket. Supplementary barrels come from their own bits.
5. Report the statistics and the CHSH value, and save the record.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Disclaimer

For education and curiosity. Given conditioned bits, every ticket is equally
likely; that is all this guarantees. Nothing here changes your odds.

MIT License.
