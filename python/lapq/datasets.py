"""Dataset extraction utilities for shortest-path prediction experiments."""

from __future__ import annotations

import argparse
import csv
import random
from array import array
from bisect import bisect_left, insort
from collections.abc import Iterable
from dataclasses import dataclass
from heapq import heappop, heappush
from math import inf
from pathlib import Path
from typing import Iterator

from .graph import CSRGraph, load_dimacs_csr


@dataclass(frozen=True)
class RelaxationEvent:
    run: int
    step: int
    source: int
    node: int
    target: int
    old_distance: float
    new_distance: float
    edge_weight: int
    queue_size: int


@dataclass(frozen=True)
class PriorityQueueInsertionEvent:
    run: int
    step: int
    source: int
    node: int
    target: int
    distance: float
    edge_weight: int
    queue_size_before: int
    predecessor_rank: int
    predecessor_distance: float | None
    predecessor_node: int | None
    predecessor_sequence: int | None


def iter_relaxation_events(
    graph: CSRGraph,
    source: int,
    max_events: int | None = None,
    run: int = 0,
) -> Iterator[RelaxationEvent]:
    """Yield successful Dijkstra relaxation events for dataset generation."""

    if source < 0 or source >= graph.num_nodes:
        raise IndexError("source out of range")
    if max_events is not None and max_events < 0:
        raise ValueError("max_events must be non-negative")

    distances = array("d", [inf]) * graph.num_nodes
    distances[source] = 0.0
    queue: list[tuple[float, int]] = [(0.0, source)]
    step = 0
    emitted = 0

    while queue:
        distance, node = heappop(queue)
        if distance != distances[node]:
            continue
        for target, weight in graph.neighbors(node):
            old_distance = distances[target]
            new_distance = distance + weight
            if new_distance >= old_distance:
                continue
            distances[target] = new_distance
            heappush(queue, (new_distance, target))
            event = RelaxationEvent(
                run=run,
                step=step,
                source=source,
                node=node,
                target=target,
                old_distance=old_distance,
                new_distance=new_distance,
                edge_weight=weight,
                queue_size=len(queue),
            )
            step += 1
            emitted += 1
            yield event
            if max_events is not None and emitted >= max_events:
                return


def collect_relaxation_events(
    graph: CSRGraph,
    source: int,
    max_events: int | None = None,
) -> list[RelaxationEvent]:
    return list(iter_relaxation_events(graph, source, max_events=max_events))


def iter_priority_queue_insertion_events(
    graph: CSRGraph,
    source: int,
    max_events: int | None = None,
    run: int = 0,
) -> Iterator[PriorityQueueInsertionEvent]:
    """Yield queue insertion events with Python-computed predecessor targets."""

    if source < 0 or source >= graph.num_nodes:
        raise IndexError("source out of range")
    if max_events is not None and max_events < 0:
        raise ValueError("max_events must be non-negative")

    distances = array("d", [inf]) * graph.num_nodes
    distances[source] = 0.0
    heap: list[tuple[float, int, int]] = [(0.0, 0, source)]
    active: list[tuple[float, int, int]] = [(0.0, 0, source)]
    next_sequence = 1
    step = 0
    emitted = 0

    while heap:
        distance, sequence, node = heappop(heap)
        _remove_active_entry(active, (distance, sequence, node))
        if distance != distances[node]:
            continue
        for target, weight in graph.neighbors(node):
            old_distance = distances[target]
            new_distance = distance + weight
            if new_distance >= old_distance:
                continue

            insertion = (new_distance, next_sequence, target)
            rank = bisect_left(active, insertion)
            predecessor = active[rank - 1] if rank > 0 else None
            event = PriorityQueueInsertionEvent(
                run=run,
                step=step,
                source=source,
                node=node,
                target=target,
                distance=new_distance,
                edge_weight=weight,
                queue_size_before=len(active),
                predecessor_rank=rank - 1,
                predecessor_distance=None if predecessor is None else predecessor[0],
                predecessor_node=None if predecessor is None else predecessor[2],
                predecessor_sequence=None if predecessor is None else predecessor[1],
            )

            distances[target] = new_distance
            heappush(heap, insertion)
            insort(active, insertion)
            next_sequence += 1
            step += 1
            emitted += 1
            yield event
            if max_events is not None and emitted >= max_events:
                return


def collect_priority_queue_insertion_events(
    graph: CSRGraph,
    source: int,
    max_events: int | None = None,
) -> list[PriorityQueueInsertionEvent]:
    return list(
        iter_priority_queue_insertion_events(graph, source, max_events=max_events)
    )


def write_relaxation_events_csv(
    events: Iterable[RelaxationEvent],
    path: str | Path,
) -> int:
    """Write relaxation events to CSV and return the number of rows."""

    rows = 0
    with Path(path).open("wt", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "run",
                "step",
                "source",
                "node",
                "target",
                "old_distance",
                "new_distance",
                "edge_weight",
                "queue_size",
            ]
        )
        for event in events:
            writer.writerow(
                [
                    event.run,
                    event.step,
                    event.source,
                    event.node,
                    event.target,
                    event.old_distance,
                    event.new_distance,
                    event.edge_weight,
                    event.queue_size,
                ]
            )
            rows += 1
    return rows


def write_priority_queue_insertion_events_csv(
    events: Iterable[PriorityQueueInsertionEvent],
    path: str | Path,
) -> int:
    rows = 0
    with Path(path).open("wt", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "run",
                "step",
                "source",
                "node",
                "target",
                "distance",
                "edge_weight",
                "queue_size_before",
                "predecessor_rank",
                "predecessor_distance",
                "predecessor_node",
                "predecessor_sequence",
            ]
        )
        for event in events:
            writer.writerow(
                [
                    event.run,
                    event.step,
                    event.source,
                    event.node,
                    event.target,
                    event.distance,
                    event.edge_weight,
                    event.queue_size_before,
                    event.predecessor_rank,
                    "" if event.predecessor_distance is None else event.predecessor_distance,
                    "" if event.predecessor_node is None else event.predecessor_node,
                    "" if event.predecessor_sequence is None else event.predecessor_sequence,
                ]
            )
            rows += 1
    return rows


def build_relaxation_dataset_csv(
    graph_path: str | Path,
    output_path: str | Path,
    source: int = 0,
    max_events: int | None = None,
) -> int:
    graph = load_dimacs_csr(graph_path)
    return write_relaxation_events_csv(
        iter_relaxation_events(graph, source, max_events=max_events),
        output_path,
    )


def build_relaxation_dataset_multi_source_csv(
    graph_path: str | Path,
    output_path: str | Path,
    sources: list[int],
    max_events_per_source: int | None = None,
) -> int:
    graph = load_dimacs_csr(graph_path)
    return write_relaxation_events_csv(
        _iter_multi_source_relaxation_events(
            graph,
            sources,
            max_events_per_source=max_events_per_source,
        ),
        output_path,
    )


def build_priority_queue_dataset_csv(
    graph_path: str | Path,
    output_path: str | Path,
    source: int = 0,
    max_events: int | None = None,
) -> int:
    graph = load_dimacs_csr(graph_path)
    return write_priority_queue_insertion_events_csv(
        iter_priority_queue_insertion_events(graph, source, max_events=max_events),
        output_path,
    )


def build_priority_queue_dataset_multi_source_csv(
    graph_path: str | Path,
    output_path: str | Path,
    sources: list[int],
    max_events_per_source: int | None = None,
) -> int:
    graph = load_dimacs_csr(graph_path)
    return write_priority_queue_insertion_events_csv(
        _iter_multi_source_priority_queue_events(
            graph,
            sources,
            max_events_per_source=max_events_per_source,
        ),
        output_path,
    )


def choose_random_sources(
    graph: CSRGraph,
    count: int,
    seed: int,
) -> list[int]:
    if count < 0:
        raise ValueError("source count must be non-negative")
    if count > graph.num_nodes:
        raise ValueError("source count exceeds graph node count")
    return random.Random(seed).sample(range(graph.num_nodes), count)


def _iter_multi_source_relaxation_events(
    graph: CSRGraph,
    sources: list[int],
    max_events_per_source: int | None,
) -> Iterator[RelaxationEvent]:
    for run, source in enumerate(sources):
        yield from iter_relaxation_events(
            graph,
            source,
            max_events=max_events_per_source,
            run=run,
        )


def _iter_multi_source_priority_queue_events(
    graph: CSRGraph,
    sources: list[int],
    max_events_per_source: int | None,
) -> Iterator[PriorityQueueInsertionEvent]:
    for run, source in enumerate(sources):
        yield from iter_priority_queue_insertion_events(
            graph,
            source,
            max_events=max_events_per_source,
            run=run,
        )


def _remove_active_entry(
    active: list[tuple[float, int, int]],
    entry: tuple[float, int, int],
) -> None:
    index = bisect_left(active, entry)
    if index >= len(active) or active[index] != entry:
        raise RuntimeError("priority queue oracle lost an active entry")
    del active[index]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a CSV dataset of successful Dijkstra relaxations."
    )
    parser.add_argument("graph", help="DIMACS .gr input graph")
    parser.add_argument("output", help="CSV output path")
    parser.add_argument(
        "--kind",
        choices=["relaxations", "queue-insertions"],
        default="queue-insertions",
        help="dataset kind to emit (default: queue-insertions)",
    )
    parser.add_argument(
        "--source",
        type=int,
        default=1,
        help="1-based DIMACS source node id (default: 1)",
    )
    parser.add_argument(
        "--sources",
        default=None,
        help="comma-separated 1-based DIMACS source ids",
    )
    parser.add_argument(
        "--source-count",
        type=int,
        default=None,
        help="number of pseudo-random sources to sample",
    )
    parser.add_argument(
        "--source-seed",
        type=int,
        default=123,
        help="seed used with --source-count (default: 123)",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="maximum number of events to emit for a single-source run",
    )
    parser.add_argument(
        "--max-events-per-source",
        type=int,
        default=None,
        help="maximum number of events to emit for each source",
    )
    args = parser.parse_args(argv)
    if args.source <= 0:
        parser.error("--source must be a positive 1-based node id")
    if args.source_count is not None and args.sources is not None:
        parser.error("--sources and --source-count are mutually exclusive")
    if args.source_count is not None and args.source_count <= 0:
        parser.error("--source-count must be positive")
    if args.max_events is not None and args.max_events < 0:
        parser.error("--max-events must be non-negative")
    if args.max_events_per_source is not None and args.max_events_per_source < 0:
        parser.error("--max-events-per-source must be non-negative")

    graph = load_dimacs_csr(args.graph)
    sources = _resolve_sources(args, graph)
    max_events_per_source = (
        args.max_events_per_source
        if args.max_events_per_source is not None
        else args.max_events
    )
    if args.kind == "relaxations":
        rows = write_relaxation_events_csv(
            _iter_multi_source_relaxation_events(
                graph,
                sources,
                max_events_per_source=max_events_per_source,
            ),
            args.output,
        )
    else:
        rows = write_priority_queue_insertion_events_csv(
            _iter_multi_source_priority_queue_events(
                graph,
                sources,
                max_events_per_source=max_events_per_source,
            ),
            args.output,
        )
    print(f"wrote {rows} {args.kind} events to {args.output}")
    return 0


def _resolve_sources(args: argparse.Namespace, graph: CSRGraph) -> list[int]:
    if args.sources is not None:
        sources = _parse_sources(args.sources)
    elif args.source_count is not None:
        sources = choose_random_sources(graph, args.source_count, args.source_seed)
    else:
        sources = [args.source - 1]

    for source in sources:
        if source < 0 or source >= graph.num_nodes:
            raise SystemExit(f"source out of range: {source + 1}")
    return sources


def _parse_sources(value: str) -> list[int]:
    sources: list[int] = []
    for raw in value.split(","):
        raw = raw.strip()
        if raw == "":
            continue
        source = int(raw)
        if source <= 0:
            raise SystemExit("sources must be positive 1-based node ids")
        sources.append(source - 1)
    if not sources:
        raise SystemExit("--sources must contain at least one source id")
    return sources


if __name__ == "__main__":
    raise SystemExit(main())
