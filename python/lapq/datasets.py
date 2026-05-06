"""Dataset extraction utilities for shortest-path prediction experiments."""

from __future__ import annotations

import argparse
import csv
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
        "--max-events",
        type=int,
        default=None,
        help="maximum number of relaxation events to emit",
    )
    args = parser.parse_args(argv)
    if args.source <= 0:
        parser.error("--source must be a positive 1-based node id")
    if args.kind == "relaxations":
        rows = build_relaxation_dataset_csv(
            args.graph,
            args.output,
            source=args.source - 1,
            max_events=args.max_events,
        )
    else:
        rows = build_priority_queue_dataset_csv(
            args.graph,
            args.output,
            source=args.source - 1,
            max_events=args.max_events,
        )
    print(f"wrote {rows} {args.kind} events to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
