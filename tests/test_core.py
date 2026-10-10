import itertools
import secrets
from collections import Counter
from math import comb

import pytest

from qdraw.bell import chsh
from qdraw.bits import BitStream, BitsExhausted, von_neumann_by_position
from qdraw.combinatorics import rank_combination, unrank_combination
from qdraw.draw import decode, replay, record_dict, build_draw
from qdraw.entropy import min_entropy_markov, min_entropy_mcv, per_position_bias, summarise
from qdraw.games import GameSpec, bits_for, get_preset, raw_bits_needed
from qdraw.sources import Sample, choose_layout, sample_os


@pytest.mark.parametrize("n,k", [(5, 2), (7, 3), (10, 4), (12, 6)])
def test_unrank_matches_itertools(n, k):
    expected = [list(c) for c in itertools.combinations(range(1, n + 1), k)]
    got = [unrank_combination(r, n, k) for r in range(comb(n, k))]
    assert got == expected
    assert [rank_combination(c, n) for c in expected] == list(range(len(expected)))


def test_unrank_big_without_memory():
    n, k = 47, 7
    last = unrank_combination(comb(n, k) - 1, n, k)
    assert last == [41, 42, 43, 44, 45, 46, 47]
    assert unrank_combination(0, n, k) == [1, 2, 3, 4, 5, 6, 7]
    with pytest.raises(ValueError):
        unrank_combination(comb(n, k), n, k)


def test_bits_for():
    assert bits_for(1) == 1
    assert bits_for(2) == 1
    assert bits_for(3) == 2
    assert bits_for(8) == 3
    assert bits_for(9) == 4
    assert bits_for(comb(45, 6)) == 23


def test_uniform_below_has_no_modulo_bias():
    # n = 5 with 3 bits: without rejection, values 0..2 would be twice as likely.
    bits = "".join(format(int.from_bytes(secrets.token_bytes(4), "big"), "032b") for _ in range(20000))
    s = BitStream(bits)
    counts = Counter()
    for _ in range(100000):
        counts[s.uniform_below(5)] += 1
    for v in range(5):
        assert abs(counts[v] / 100000 - 0.2) < 0.01
    assert s.rejections > 0


def test_bitstream_exhaustion():
    s = BitStream("1010")
    assert s.take(3) == 5
    with pytest.raises(BitsExhausted):
        s.take(2)


def test_von_neumann_debiases_per_position():
    import random
    rnd = random.Random(1)
    # position 0 heavily biased, position 1 fair
    shots = ["".join(("1" if rnd.random() < 0.8 else "0", "1" if rnd.random() < 0.5 else "0")) for _ in range(40000)]
    out = von_neumann_by_position(shots)
    assert abs(out.count("1") / len(out) - 0.5) < 0.02
    # pairs that agree produce nothing
    assert von_neumann_by_position(["11", "11", "00", "00"]) == ""
    assert von_neumann_by_position(["10", "01"]) == "10"


def test_min_entropy_estimators():
    fair = "".join(format(int.from_bytes(secrets.token_bytes(4), "big"), "032b") for _ in range(4000))
    assert min_entropy_mcv(fair) > 0.97
    assert min_entropy_markov(fair) > 0.97
    assert min_entropy_mcv("0" * 1000) == 0.0
    assert min_entropy_markov("01" * 2000) < 0.05  # perfectly predictable alternation
    biased = "".join("1" if secrets.randbelow(100) < 75 else "0" for _ in range(20000))
    assert 0.35 < min_entropy_mcv(biased) < 0.45  # -log2(0.75) = 0.415


def test_per_position_bias():
    assert per_position_bias(["10", "11", "00", "10"]) == [0.75, 0.25]


def test_chsh_ideal_and_classical():
    # Perfectly correlated classical bits: every setting E=1 -> S = 1+1+1-1 = 2 (classical bound)
    assert abs(chsh(["00000000"] * 100)["S"] - 2.0) < 1e-9
    r = chsh(["01" * 4] * 100)
    assert abs(r["S"] + 2.0) < 1e-9  # every setting E=-1 -> S = -2
    assert not r["violates_classical"]


def test_decode_is_deterministic_and_valid():
    spec = get_preset("powerball")
    shots = sample_os(raw_bits_needed(spec, 10, True)).rng_shots
    a = decode(spec, 10, shots, "von_neumann")
    b = decode(spec, 10, shots, "von_neumann")
    assert [g.main for g in a["games"]] == [g.main for g in b["games"]]
    for g in a["games"]:
        assert len(g.main) == 7 and len(set(g.main)) == 7 and all(1 <= x <= 35 for x in g.main)
        assert g.main == sorted(g.main)
        assert len(g.supp) == 1 and 1 <= g.supp[0] <= 20


def test_bits_needed_is_sufficient_for_many_games():
    for name in ("saturday", "ozlotto", "powerball", "setforlife"):
        spec = get_preset(name)
        for cond in ("von_neumann", "none"):
            sample = sample_os(raw_bits_needed(spec, 50, cond == "von_neumann"))
            d = decode(spec, 50, sample.rng_shots, cond)
            assert len(d["games"]) == 50


def test_replay_reproduces_record(tmp_path):
    spec = get_preset("ozlotto")
    sample = sample_os(raw_bits_needed(spec, 5, True))
    d = build_draw(spec, 5, sample, "von_neumann")
    rec = record_dict(d)
    d2 = replay(rec)
    assert [g.main for g in d2.games] == [g.main for g in d.games]
    assert d2.entropy_raw["min_entropy_mcv"] == d.entropy_raw["min_entropy_mcv"]


def test_choose_layout_prefers_low_readout_error():
    errors = {q: 0.001 * (q + 1) for q in range(20)}
    errors[3] = 0.5  # bad qubit
    edges = [(q, q + 1) for q in range(19)]
    rng_q, bell_q = choose_layout(errors, edges, faulty={19}, n_rng=6, bell=True)
    assert 3 not in bell_q  # 0.5 readout error exceeds the cutoff
    assert len(bell_q) == 8 and len(set(bell_q)) == 8
    assert all((a, b) in edges or (b, a) in edges for a, b in zip(bell_q[::2], bell_q[1::2]))
    assert len(rng_q) == 6 and 3 not in rng_q and 19 not in rng_q
    assert not set(rng_q) & set(bell_q)


def test_choose_layout_excludes_noisy_qubits_when_unlimited():
    errors = {q: 0.01 for q in range(12)}
    errors[4] = 0.33
    rng_q, bell_q = choose_layout(errors, [], faulty=set(), n_rng=None, bell=False)
    assert 4 not in rng_q and len(rng_q) == 11


def test_gamespec_validation():
    with pytest.raises(ValueError):
        GameSpec("x", 50, 45)
    assert get_preset("lotto").pool == 45
    with pytest.raises(KeyError):
        get_preset("nope")


def test_summarise_has_expected_keys():
    s = summarise("0110" * 100, ["0110"] * 100)
    assert s["positions"] == 4
    assert s["per_position_ones"] == [0.0, 1.0, 1.0, 0.0]
