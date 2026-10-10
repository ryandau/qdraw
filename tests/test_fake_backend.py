"""Run the full IBM code path on a fake backend with that chip's real calibration data."""
import pytest

pytest.importorskip("qiskit_aer")
from qiskit_ibm_runtime.fake_provider import FakeTorino  # noqa: E402

from qdraw.draw import build_draw
from qdraw.games import get_preset, raw_bits_needed
from qdraw.sources import sample_ibm


def test_sample_ibm_on_fake_torino():
    spec = get_preset("saturday")
    backend = FakeTorino()
    sample = sample_ibm(raw_bits_needed(spec, 4, True), bell=True, n_qubits=12, shots=300,
                        backend=backend, log=lambda m: None)
    assert sample.width == 12 and sample.shots == 300
    assert len(sample.bell_shots) == 300 and len(sample.bell_shots[0]) == 8
    assert len(sample.layout["rng"]) == 12 and len(sample.layout["bell"]) == 8
    assert not set(sample.layout["rng"]) & set(sample.layout["bell"])
    d = build_draw(spec, 4, sample, "von_neumann")
    assert len(d.games) == 4
    assert d.bell["available"] and d.bell["S"] > 2.0  # noisy but should still violate
    assert all(v is not None for v in sample.readout_errors.values())
