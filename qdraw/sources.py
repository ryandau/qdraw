"""
Bit sources: IBM Quantum hardware, a local ideal simulator, or the OS CSPRNG.

Every source returns a Sample: per-shot bit strings for the RNG register
(index i == qubit i), optional per-shot strings for the 8-qubit Bell register,
and provenance.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from math import ceil
from typing import Dict, List, Optional, Sequence, Tuple

from .bell import N_BELL_QUBITS, add_bell_pairs

SIM_WIDTH = 16  # qubits per simulated RNG circuit; keeps the statevector small


@dataclass
class Sample:
    source: str
    rng_shots: List[str]
    bell_shots: Optional[List[str]]
    backend: str
    job_id: Optional[str] = None
    layout: Dict[str, List[int]] = field(default_factory=dict)
    readout_errors: Dict[int, Optional[float]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def width(self) -> int:
        return len(self.rng_shots[0]) if self.rng_shots else 0

    @property
    def shots(self) -> int:
        return len(self.rng_shots)


def _little_to_big(s: str) -> str:
    """Qiskit prints clbit 0 on the right. Reverse so index i == clbit i."""
    return s[::-1]


# ----------------------------------------------------------------------------- OS

def _shot_count(raw_bits: int, width: int, shots: Optional[int], min_shots: int) -> int:
    n = shots if shots is not None else max(min_shots, ceil(raw_bits / width))
    return n + (n % 2)


def sample_os(raw_bits: int, width: int = 64, shots: Optional[int] = None, min_shots: int = 2) -> Sample:
    shots = _shot_count(raw_bits, width, shots, min_shots)
    rng = []
    for _ in range(shots):
        n = int.from_bytes(secrets.token_bytes(ceil(width / 8)), "big")
        rng.append(format(n, f"0{width * 2}b")[-width:])
    return Sample("os", rng, None, "secrets (OS CSPRNG)", notes=["no Bell test for a classical source"])


# ---------------------------------------------------------------------- simulator

def sample_sim(raw_bits: int, bell: bool = True, width: int = SIM_WIDTH,
               shots: Optional[int] = None, min_shots: int = 2) -> Sample:
    from qiskit import QuantumCircuit, transpile
    from qiskit.providers.basic_provider import BasicSimulator

    sim = BasicSimulator()
    shots = _shot_count(raw_bits, width, shots, min_shots)

    qc = QuantumCircuit(width, width)
    qc.h(range(width))
    qc.measure(range(width), range(width))
    mem = sim.run(transpile(qc, sim), shots=shots, memory=True).result().get_memory()
    rng = [_little_to_big(m) for m in mem]

    bell_shots = None
    if bell:
        bq = QuantumCircuit(N_BELL_QUBITS, N_BELL_QUBITS)
        add_bell_pairs(bq, list(range(N_BELL_QUBITS)), list(range(N_BELL_QUBITS)))
        bmem = sim.run(transpile(bq, sim), shots=shots, memory=True).result().get_memory()
        bell_shots = [_little_to_big(m) for m in bmem]

    return Sample("sim", rng, bell_shots, "BasicSimulator (ideal, noiseless)",
                  layout={"rng": list(range(width)), "bell": list(range(N_BELL_QUBITS))})


# ---------------------------------------------------------------------------- IBM

def connect(token: Optional[str] = None, instance: Optional[str] = None):
    from qiskit_ibm_runtime import QiskitRuntimeService

    token = token or os.environ.get("QISKIT_IBM_TOKEN")
    instance = instance or os.environ.get("QISKIT_IBM_INSTANCE")
    kwargs = {}
    if token:
        kwargs.update(channel="ibm_quantum_platform", token=token)
    if instance:
        kwargs["instance"] = instance
    return QiskitRuntimeService(**kwargs)


def save_account(token: str, instance: Optional[str] = None) -> None:
    from qiskit_ibm_runtime import QiskitRuntimeService

    QiskitRuntimeService.save_account(
        channel="ibm_quantum_platform", token=token, instance=instance, overwrite=True
    )


def readout_errors(backend) -> Dict[int, Optional[float]]:
    errs: Dict[int, Optional[float]] = {}
    try:
        meas = backend.target["measure"]
        for (q,), props in meas.items():
            errs[q] = getattr(props, "error", None) if props is not None else None
    except Exception:
        for q in range(backend.num_qubits):
            errs[q] = None
    return errs


def faulty_qubits(backend) -> set:
    try:
        return set(backend.properties().faulty_qubits())
    except Exception:
        return set()


def choose_layout(
    errors: Dict[int, Optional[float]],
    edges: Sequence[Tuple[int, int]],
    faulty: set,
    n_rng: Optional[int],
    bell: bool,
) -> Tuple[List[int], List[int]]:
    """Pick Bell pairs on the cleanest coupled qubits, then RNG qubits by readout error."""
    good = {q: e for q, e in errors.items() if q not in faulty and e is not None}
    if not good:
        good = {q: 0.0 for q in errors if q not in faulty}

    bell_q: List[int] = []
    if bell:
        scored = sorted(
            ((good[a] + good[b], a, b) for a, b in edges if a in good and b in good),
        )
        used = set()
        for _, a, b in scored:
            if a in used or b in used:
                continue
            bell_q += [a, b]
            used.update((a, b))
            if len(bell_q) == N_BELL_QUBITS:
                break
        if len(bell_q) < N_BELL_QUBITS:
            raise RuntimeError("could not find 4 disjoint coupled qubit pairs for the Bell test")

    pool = sorted((q for q in good if q not in bell_q), key=lambda q: good[q])
    if n_rng is not None:
        pool = pool[:n_rng]
    if not pool:
        raise RuntimeError("no qubits left for the RNG register")
    return sorted(pool), bell_q


def sample_ibm(
    raw_bits: int,
    bell: bool = True,
    backend_name: Optional[str] = None,
    n_qubits: Optional[int] = None,
    shots: Optional[int] = None,
    min_shots: int = 256,
    token: Optional[str] = None,
    instance: Optional[str] = None,
    service=None,
    backend=None,
    log=print,
) -> Sample:
    from qiskit import QuantumCircuit, ClassicalRegister, QuantumRegister
    from qiskit.transpiler import generate_preset_pass_manager
    from qiskit_ibm_runtime import SamplerV2

    if backend is None:
        service = service or connect(token, instance)
        need_q = (n_qubits or 1) + (N_BELL_QUBITS if bell else 0)
        if backend_name:
            backend = service.backend(backend_name)
        else:
            backend = service.least_busy(operational=True, simulator=False, min_num_qubits=need_q)
    log(f"backend: {backend.name} ({backend.num_qubits} qubits)")

    errs = readout_errors(backend)
    faulty = faulty_qubits(backend)
    edges = list(backend.coupling_map.get_edges()) if backend.coupling_map else []
    rng_q, bell_q = choose_layout(errs, edges, faulty, n_qubits, bell)

    width = len(rng_q)
    shots = _shot_count(raw_bits, width, shots, min_shots)

    qr = QuantumRegister(width + len(bell_q), "q")
    cr_rng = ClassicalRegister(width, "rng")
    qc = QuantumCircuit(qr, cr_rng)
    if bell:
        cr_bell = ClassicalRegister(N_BELL_QUBITS, "bell")
        qc.add_register(cr_bell)
    qc.h(qr[:width])
    qc.measure(qr[:width], cr_rng)
    if bell:
        add_bell_pairs(qc, list(qr[width:]), list(cr_bell))

    initial_layout = rng_q + bell_q
    pm = generate_preset_pass_manager(optimization_level=1, backend=backend, initial_layout=initial_layout)
    isa = pm.run(qc)

    sampler = SamplerV2(mode=backend)
    # Keep the bits raw: no twirling, no dynamical decoupling.
    try:
        sampler.options.twirling.enable_gates = False
        sampler.options.twirling.enable_measure = False
        sampler.options.dynamical_decoupling.enable = False
    except Exception:
        pass

    log(f"submitting: {width} RNG qubits" + (" + 8 Bell qubits" if bell else "") + f", {shots} shots")
    job = sampler.run([isa], shots=shots)
    log(f"job id: {job.job_id()}  (waiting for the queue...)")
    result = job.result()

    data = result[0].data
    rng = [_little_to_big(s) for s in data.rng.get_bitstrings()]
    bell_shots = [_little_to_big(s) for s in data.bell.get_bitstrings()] if bell else None
    return Sample(
        "ibm", rng, bell_shots, backend.name, job.job_id(),
        layout={"rng": rng_q, "bell": bell_q},
        readout_errors={q: errs.get(q) for q in initial_layout},
    )


def fetch_ibm_job(job_id: str, token: Optional[str] = None, instance: Optional[str] = None, service=None) -> Sample:
    """Re-download a past job's measurements so a draw can be recomputed."""
    service = service or connect(token, instance)
    job = service.job(job_id)
    result = job.result()
    data = result[0].data
    rng = [_little_to_big(s) for s in data.rng.get_bitstrings()]
    bell_shots = None
    if hasattr(data, "bell"):
        bell_shots = [_little_to_big(s) for s in data.bell.get_bitstrings()]
    try:
        backend = job.backend().name
    except Exception:
        backend = "unknown"
    return Sample("ibm", rng, bell_shots, backend, job_id)
