# How qdraw works, and how to read its output

## The problem with "quantum random"

A qubit put into superposition and measured gives 0 or 1 with no way, even in
principle, to predict which. That is the physics. The engineering is messier:

- **Readout error.** Current IBM processors misread a qubit around 0.5 to 3% of
  the time, and the error is asymmetric, so measured bits lean toward 0.
- **Crosstalk.** Measuring one qubit can slightly disturb its neighbours, so
  neighbouring bits are weakly correlated.
- **Drift.** Both of the above change hour to hour as the machine is recalibrated.

So raw bits from the machine are physically random but statistically imperfect.
Any tool that prints them as-is and calls them "truly random" is overselling.

## What qdraw does about it

### 1. Qubit selection

The backend publishes a calibration table with each qubit's readout error.
qdraw sorts by that and uses the cleanest qubits for the random bits. Faulty
qubits are skipped. The four Bell pairs go on the lowest-error pairs of qubits
that are physically connected.

### 2. One circuit, many shots

Every RNG qubit gets a Hadamard gate and a measurement. Depth one, so there is
almost no time for decoherence. The circuit is run for many shots (minimum 256).
Shots are cheap; qubits are what the chip limits. A 127-qubit chip at 256 shots
gives about 30,000 raw bits in a single job, enough for hundreds of games.

Measurement twirling and dynamical decoupling are disabled so the statistics
describe the hardware, not IBM's error mitigation.

### 3. Conditioning (von Neumann extraction)

For each qubit, take its bits from shot 1 and shot 2, shot 3 and shot 4, and so
on. If the pair is `01` emit 0; if `10` emit 1; if `00` or `11` emit nothing.

This is the one situation where von Neumann's 1951 trick is exactly right:
the two bits in a pair come from the same qubit with the same bias and are
independent because the shots are independent. The output bits are then
unbiased no matter what the bias was. About a quarter of the raw bits survive.

### 4. Decoding without modulo bias

Saturday Lotto has 8,145,060 possible tickets. Reading 23 bits gives a number up
to 8,388,607. Taking it modulo 8,145,060, which is what the first version of
this project did, makes the first 243,548 tickets twice as likely as the rest.

qdraw instead reads 23 bits, and if the value is 8,145,060 or more it throws it
away and reads another 23. About 3% are rejected. Every ticket ends up exactly
equally likely.

The accepted index is turned into a ticket with the combinatorial number
system, which computes the k-th combination directly. Nothing is enumerated,
so Oz Lotto's 62.9 million combinations cost the same as a 6-from-45 game.

### 5. Bell test

Eight qubits in each job form four entangled pairs, each measured in one of the
four CHSH settings. From the results qdraw computes

    S = E(a,b) + E(a,b') + E(a',b) - E(a',b')

Any explanation of the pairs in terms of pre-existing classical values gives
|S| <= 2. Quantum mechanics allows up to 2.83. A result clearly above 2 shows
the hardware produced genuinely entangled states during this job.

Be clear about what this is and is not. It is a sanity check that the processor
was behaving quantum mechanically at the time, run on the same chip in the same
job as your numbers. It is not a loophole-free Bell test and not a
device-independent randomness certificate; those need space-like separation and
near-perfect detection that no cloud machine provides.

### 6. Records and audit

Each draw writes a JSON file to `~/.qdraw/draws/` (override with `QDRAW_HOME`)
containing the game, qubits used, every measured bit, the games, and all the
statistics. `qdraw audit <job_id>` re-downloads the job's results from IBM,
recomputes the games, and checks they match. `qdraw audit --record FILE` does
the same offline. Replay trusts IBM's stored job result; it does not re-measure.

## Reading the report

```
  raw bits        31,744 from 124 qubits x 256 shots, ones 0.489, worst qubit 87 at 0.441
  min-entropy     0.934 per raw bit (1.000 is perfect)
  conditioned     7,802 bits kept (25%), ones 0.501, 84 used for 3 games
  Bell test       S = 2.64 +/- 0.03  (classical <= 2, quantum <= 2.83)  non-classical
```

- **ones**: fraction of 1s. Ideal is 0.500. Raw hardware typically shows 0.48
  to 0.50 overall with the odd qubit at 0.44. After conditioning it should sit
  at 0.50 within sampling noise (roughly +/- 1/sqrt(n)).
- **worst qubit**: the physical qubit index with the largest lean. Useful for
  spotting a qubit the calibration table flattered.
- **min-entropy per raw bit**: the NIST SP 800-90B most-common-value estimate.
  It answers "how many bits of genuine unpredictability per measured bit", as a
  99% confidence bound. 1.0 is perfect. Because it is a bound, it reads lower on
  small samples; `-v` shows it for the conditioned bits with the sample size.
- **conditioned / used**: how many clean bits the job produced and how many the
  games consumed. Each Saturday Lotto game needs about 23.7 bits on average.
- **Bell S**: above 2 by several standard errors is a pass. Noisy hardware
  gives roughly 2.5 to 2.75; the simulator approaches 2.83. If a job comes back
  near or below 2, the chip was having a bad moment and the RNG bits from that
  job deserve more suspicion, not less.

`qdraw draw -v` adds Shannon entropy, the Markov min-entropy estimate, lag-1
serial correlation, a runs test, the four CHSH correlators, the readout errors
of the chosen qubits, and the physical qubit layout.

## An honest comparison

Run the same statistics on bits from a local simulator and from your operating
system's random generator and the raw hardware bits will score worst of the
three until they are conditioned. That is expected and is the whole reason the
conditioning step exists. The quantum source is not better at being random than
a good CSPRNG. Its claim is different: the unpredictability is physical rather
than computational, and this tool lets you check how much of it survived the
electronics.
