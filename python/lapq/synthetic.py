"""Synthetic hint experiments for the LAPQ Python bindings."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from ._lapq import Handle, PriorityQueue

InsertionScenario = Literal["baseline", "perfect", "noisy", "bad_left"]


@dataclass(frozen=True)
class InsertionResult:
    scenario: str
    n: int
    noise: int
    seconds: float
    stats: dict[str, int]
    avg_error: float
    max_error: int
    checksum: int


def run_insertion_scenario(
    n: int,
    scenario: InsertionScenario,
    noise: int = 64,
) -> InsertionResult:
    """Run a synthetic increasing-key insertion experiment.

    The prediction policy lives entirely in Python. The C extension only sees
    opaque predecessor handles and remains responsible for validation and
    correction.
    """

    if n < 0:
        raise ValueError("n must be non-negative")
    if noise < 0:
        raise ValueError("noise must be non-negative")
    if scenario not in {"baseline", "perfect", "noisy", "bad_left"}:
        raise ValueError(f"unknown insertion scenario: {scenario!r}")

    queue = PriorityQueue()
    handles: list[Handle | None] = [None] * n
    total_error = 0
    max_error = 0
    start = perf_counter()

    for index in range(n):
        key = float(index)
        if scenario == "baseline" or index == 0:
            if scenario == "baseline":
                queue.push(key, index)
            else:
                handles[index] = queue.push_handle(key, index)
            continue

        if scenario == "perfect":
            predecessor = index - 1
        elif scenario == "noisy":
            predecessor = index - min(noise, index - 1) - 1
        else:
            predecessor = 0

        error = index - predecessor - 1
        total_error += error
        max_error = max(max_error, error)
        predecessor_handle = handles[predecessor]
        if predecessor_handle is None:
            raise RuntimeError("missing predecessor handle")
        handles[index] = queue.push_with_predecessor(key, index, predecessor_handle)

    checksum = 0
    while not queue.empty():
        _, value = queue.pop()
        checksum += int(value)

    hinted = max(n - 1, 0) if scenario != "baseline" else 0
    avg_error = total_error / hinted if hinted else 0.0
    return InsertionResult(
        scenario=scenario,
        n=n,
        noise=noise,
        seconds=perf_counter() - start,
        stats=queue.stats(),
        avg_error=avg_error,
        max_error=max_error,
        checksum=checksum,
    )
