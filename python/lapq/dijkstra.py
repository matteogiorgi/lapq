"""Dijkstra implementations used by the Python experiment layer."""

from __future__ import annotations

import argparse
import csv
import sys
from array import array
from bisect import bisect_left, insort
from dataclasses import dataclass
from heapq import heappop, heappush
from math import inf
from pathlib import Path
from time import perf_counter
from typing import Literal

from ._lapq import Handle, PriorityQueue
from .graph import CSRGraph, load_dimacs_csr

DijkstraBackend = Literal["heapq", "lapq"]
DijkstraHintScenario = Literal["baseline", "perfect", "noisy", "bad_left", "rank"]


@dataclass(frozen=True)
class DijkstraResult:
    source: int
    distances: array
    seconds: float
    settled: int
    relaxations: int
    stale_pops: int
    queue_stats: dict[str, int] | None = None
    avg_hint_error: float = 0.0
    max_hint_error: int = 0


@dataclass(frozen=True)
class DijkstraBenchmarkRow:
    backend: str
    source: int
    seconds: float
    settled: int
    relaxations: int
    stale_pops: int
    hint_scenario: str = ""
    avg_hint_error: float = 0.0
    max_hint_error: int = 0
    clean_comparisons: int | None = None


def dijkstra(
    graph: CSRGraph,
    source: int,
    backend: DijkstraBackend = "heapq",
) -> DijkstraResult:
    if backend == "heapq":
        return dijkstra_heapq(graph, source)
    if backend == "lapq":
        return dijkstra_lapq(graph, source)
    raise ValueError(f"unknown Dijkstra backend: {backend!r}")


def benchmark_dijkstra_backends(
    graph: CSRGraph,
    source: int,
    backends: tuple[DijkstraBackend, ...] = ("heapq", "lapq"),
) -> list[DijkstraBenchmarkRow]:
    rows: list[DijkstraBenchmarkRow] = []
    for backend in backends:
        result = dijkstra(graph, source, backend=backend)
        queue_stats = result.queue_stats or {}
        rows.append(
            DijkstraBenchmarkRow(
                backend=backend,
                source=source,
                seconds=result.seconds,
                settled=result.settled,
                relaxations=result.relaxations,
                stale_pops=result.stale_pops,
                hint_scenario="",
                avg_hint_error=result.avg_hint_error,
                max_hint_error=result.max_hint_error,
                clean_comparisons=queue_stats.get("clean_comparisons"),
            )
        )
    return rows


def benchmark_dijkstra_hint_scenarios(
    graph: CSRGraph,
    source: int,
    scenarios: tuple[DijkstraHintScenario, ...] = (
        "baseline",
        "perfect",
        "noisy",
        "bad_left",
        "rank",
    ),
    noise: int = 64,
) -> list[DijkstraBenchmarkRow]:
    rows: list[DijkstraBenchmarkRow] = []
    for scenario in scenarios:
        result = dijkstra_lapq_hinted(graph, source, scenario=scenario, noise=noise)
        queue_stats = result.queue_stats or {}
        rows.append(
            DijkstraBenchmarkRow(
                backend="lapq",
                source=source,
                seconds=result.seconds,
                settled=result.settled,
                relaxations=result.relaxations,
                stale_pops=result.stale_pops,
                hint_scenario=scenario,
                avg_hint_error=result.avg_hint_error,
                max_hint_error=result.max_hint_error,
                clean_comparisons=queue_stats.get("clean_comparisons"),
            )
        )
    return rows


def write_dijkstra_benchmark_csv(
    rows: list[DijkstraBenchmarkRow],
    path: str | Path,
) -> None:
    with Path(path).open("wt", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "backend",
                "source",
                "seconds",
                "settled",
                "relaxations",
                "stale_pops",
                "hint_scenario",
                "avg_hint_error",
                "max_hint_error",
                "clean_comparisons",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.backend,
                    row.source + 1,
                    row.seconds,
                    row.settled,
                    row.relaxations,
                    row.stale_pops,
                    row.hint_scenario,
                    row.avg_hint_error,
                    row.max_hint_error,
                    "" if row.clean_comparisons is None else row.clean_comparisons,
                ]
            )


def dijkstra_heapq(graph: CSRGraph, source: int) -> DijkstraResult:
    _check_source(graph, source)
    distances = _initial_distances(graph.num_nodes, source)
    queue: list[tuple[float, int]] = [(0.0, source)]
    settled = 0
    relaxations = 0
    stale_pops = 0
    start = perf_counter()

    while queue:
        distance, node = heappop(queue)
        if distance != distances[node]:
            stale_pops += 1
            continue
        settled += 1
        for target, weight in graph.neighbors(node):
            candidate = distance + weight
            if candidate < distances[target]:
                distances[target] = candidate
                relaxations += 1
                heappush(queue, (candidate, target))

    return DijkstraResult(
        source=source,
        distances=distances,
        seconds=perf_counter() - start,
        settled=settled,
        relaxations=relaxations,
        stale_pops=stale_pops,
    )


def dijkstra_lapq(graph: CSRGraph, source: int) -> DijkstraResult:
    _check_source(graph, source)
    distances = _initial_distances(graph.num_nodes, source)
    queue = PriorityQueue()
    queue.push(0.0, source)
    settled = 0
    relaxations = 0
    stale_pops = 0
    start = perf_counter()

    while not queue.empty():
        distance, node = queue.pop()
        if distance != distances[node]:
            stale_pops += 1
            continue
        settled += 1
        for target, weight in graph.neighbors(node):
            candidate = distance + weight
            if candidate < distances[target]:
                distances[target] = candidate
                relaxations += 1
                queue.push(candidate, target)

    return DijkstraResult(
        source=source,
        distances=distances,
        seconds=perf_counter() - start,
        settled=settled,
        relaxations=relaxations,
        stale_pops=stale_pops,
        queue_stats=queue.stats(),
    )


def dijkstra_lapq_hinted(
    graph: CSRGraph,
    source: int,
    scenario: DijkstraHintScenario,
    noise: int = 64,
) -> DijkstraResult:
    """Run Dijkstra with synthetic predecessor/rank hints generated in Python."""

    if scenario not in {"baseline", "perfect", "noisy", "bad_left", "rank"}:
        raise ValueError(f"unknown Dijkstra hint scenario: {scenario!r}")
    if noise < 0:
        raise ValueError("noise must be non-negative")

    _check_source(graph, source)
    distances = _initial_distances(graph.num_nodes, source)
    queue = PriorityQueue()
    first_handle = queue.push_handle(0.0, (0, source))
    heap: list[tuple[float, int, int]] = [(0.0, 0, source)]
    active: list[tuple[float, int, int, Handle]] = [(0.0, 0, source, first_handle)]
    next_sequence = 1
    settled = 0
    relaxations = 0
    stale_pops = 0
    hinted = 0
    total_error = 0
    max_error = 0
    start = perf_counter()

    while not queue.empty():
        distance, payload = queue.pop()
        sequence, node = payload
        _remove_active_handle(active, (distance, sequence, node))
        heap_distance, heap_sequence, heap_node = heappop(heap)
        if (heap_distance, heap_sequence, heap_node) != (distance, sequence, node):
            raise RuntimeError("LAPQ and Python oracle priority queues diverged")
        if distance != distances[node]:
            stale_pops += 1
            continue
        settled += 1
        for target, weight in graph.neighbors(node):
            candidate = distance + weight
            if candidate >= distances[target]:
                continue

            rank = bisect_left(active, (candidate, next_sequence, target))
            predecessor_rank = _predicted_predecessor_rank(
                active,
                rank,
                scenario,
                noise,
            )
            error = _hint_error_from_predecessor_rank(rank, predecessor_rank)
            handle = _push_hinted_entry(
                queue,
                active,
                candidate,
                next_sequence,
                target,
                rank,
                scenario,
                predecessor_rank,
            )
            total_error += error
            max_error = max(max_error, error)
            hinted += 0 if scenario == "baseline" else 1

            distances[target] = candidate
            heappush(heap, (candidate, next_sequence, target))
            insort(active, (candidate, next_sequence, target, handle))
            next_sequence += 1
            relaxations += 1

    return DijkstraResult(
        source=source,
        distances=distances,
        seconds=perf_counter() - start,
        settled=settled,
        relaxations=relaxations,
        stale_pops=stale_pops,
        queue_stats=queue.stats(),
        avg_hint_error=total_error / hinted if hinted else 0.0,
        max_hint_error=max_error,
    )


def _initial_distances(num_nodes: int, source: int) -> array:
    distances = array("d", [inf]) * num_nodes
    distances[source] = 0.0
    return distances


def _check_source(graph: CSRGraph, source: int) -> None:
    if source < 0 or source >= graph.num_nodes:
        raise IndexError("source out of range")


def _push_hinted_entry(
    queue: PriorityQueue,
    active: list[tuple[float, int, int, Handle]],
    distance: float,
    sequence: int,
    node: int,
    rank: int,
    scenario: DijkstraHintScenario,
    predecessor_rank: int | None,
) -> Handle:
    value = (sequence, node)
    if scenario == "baseline" or not active:
        return queue.push_handle(distance, value)
    if scenario == "rank":
        return queue.push_with_rank(distance, value, rank)

    if predecessor_rank is None:
        return queue.push_handle(distance, value)
    return queue.push_with_predecessor(distance, value, active[predecessor_rank][3])


def _predicted_predecessor_rank(
    active: list[tuple[float, int, int, Handle]],
    rank: int,
    scenario: DijkstraHintScenario,
    noise: int,
) -> int | None:
    true_predecessor = rank - 1
    if true_predecessor < 0:
        return None
    if scenario == "perfect":
        return true_predecessor
    if scenario == "noisy":
        return max(0, true_predecessor - noise)
    if scenario == "bad_left":
        return 0
    return None


def _hint_error_from_predecessor_rank(
    rank: int,
    predecessor_rank: int | None,
) -> int:
    true_predecessor = rank - 1
    if predecessor_rank is None or true_predecessor < 0:
        return 0
    return abs(true_predecessor - predecessor_rank)


def _remove_active_handle(
    active: list[tuple[float, int, int, Handle]],
    entry: tuple[float, int, int],
) -> None:
    index = bisect_left(active, entry)
    if index >= len(active) or active[index][:3] != entry:
        raise RuntimeError("priority queue oracle lost an active entry")
    del active[index]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Dijkstra on a DIMACS graph with heapq and/or LAPQ."
    )
    parser.add_argument("graph", help="DIMACS .gr input graph")
    parser.add_argument(
        "--source",
        type=int,
        default=1,
        help="1-based DIMACS source node id (default: 1)",
    )
    parser.add_argument(
        "--backend",
        choices=["heapq", "lapq", "both", "lapq-hints"],
        default="both",
        help="backend to run (default: both)",
    )
    parser.add_argument(
        "--hint-scenario",
        choices=["baseline", "perfect", "noisy", "bad_left", "rank", "all"],
        default="all",
        help="LAPQ hint scenario used with --backend lapq-hints (default: all)",
    )
    parser.add_argument(
        "--noise",
        type=int,
        default=64,
        help="rank/predecessor noise for synthetic hint scenarios",
    )
    parser.add_argument("--csv", help="optional CSV output path")
    args = parser.parse_args(argv)
    if args.source <= 0:
        parser.error("--source must be a positive 1-based node id")

    graph = load_dimacs_csr(args.graph)
    if args.noise < 0:
        parser.error("--noise must be non-negative")
    if args.backend == "lapq-hints":
        if args.hint_scenario == "all":
            scenarios: tuple[DijkstraHintScenario, ...] = (
                "baseline",
                "perfect",
                "noisy",
                "bad_left",
                "rank",
            )
        else:
            scenarios = (args.hint_scenario,)
        rows = benchmark_dijkstra_hint_scenarios(
            graph,
            args.source - 1,
            scenarios=scenarios,
            noise=args.noise,
        )
    else:
        if args.backend == "both":
            backends: tuple[DijkstraBackend, ...] = ("heapq", "lapq")
        else:
            backends = (args.backend,)
        rows = benchmark_dijkstra_backends(graph, args.source - 1, backends=backends)

    output = sys.stdout
    writer = csv.writer(output)
    writer.writerow(
        [
            "backend",
            "source",
            "seconds",
            "settled",
            "relaxations",
            "stale_pops",
            "hint_scenario",
            "avg_hint_error",
            "max_hint_error",
            "clean_comparisons",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.backend,
                row.source + 1,
                f"{row.seconds:.9f}",
                row.settled,
                row.relaxations,
                row.stale_pops,
                row.hint_scenario,
                f"{row.avg_hint_error:.6f}",
                row.max_hint_error,
                "" if row.clean_comparisons is None else row.clean_comparisons,
            ]
        )
    if args.csv is not None:
        write_dijkstra_benchmark_csv(rows, args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
