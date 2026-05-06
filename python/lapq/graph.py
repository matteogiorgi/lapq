"""Compact graph storage and DIMACS shortest-path graph loading."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class CSRGraph:
    """Directed weighted graph stored in compressed sparse row form."""

    num_nodes: int
    offsets: array
    targets: array
    weights: array

    @property
    def num_edges(self) -> int:
        return len(self.targets)

    def neighbors(self, node: int) -> Iterator[tuple[int, int]]:
        if node < 0 or node >= self.num_nodes:
            raise IndexError("node out of range")
        begin = self.offsets[node]
        end = self.offsets[node + 1]
        for index in range(begin, end):
            yield self.targets[index], self.weights[index]

    def out_degree(self, node: int) -> int:
        if node < 0 or node >= self.num_nodes:
            raise IndexError("node out of range")
        return self.offsets[node + 1] - self.offsets[node]


def load_dimacs_csr(path: str | Path) -> CSRGraph:
    """Load a DIMACS shortest-path graph into CSR arrays.

    DIMACS `.gr` files use 1-based node ids and lines of the form
    `p sp <nodes> <arcs>` and `a <source> <target> <weight>`. The loader uses
    two passes so large graphs are not materialized as Python edge tuples.
    """

    graph_path = Path(path)
    num_nodes, num_edges = _read_problem_line(graph_path)
    degrees = array("Q", [0]) * num_nodes

    with graph_path.open("rt", encoding="ascii") as file:
        for line in file:
            if not line or line[0] != "a":
                continue
            source, _, _ = _parse_arc(line, num_nodes)
            degrees[source] += 1

    offsets = array("Q", [0]) * (num_nodes + 1)
    running = 0
    for node, degree in enumerate(degrees):
        offsets[node] = running
        running += degree
    offsets[num_nodes] = running
    if running != num_edges:
        raise ValueError(
            f"DIMACS arc count mismatch: header says {num_edges}, found {running}"
        )

    targets = array("I", [0]) * num_edges
    weights = array("I", [0]) * num_edges
    cursor = array("Q", offsets)

    with graph_path.open("rt", encoding="ascii") as file:
        for line in file:
            if not line or line[0] != "a":
                continue
            source, target, weight = _parse_arc(line, num_nodes)
            index = cursor[source]
            targets[index] = target
            weights[index] = weight
            cursor[source] += 1

    return CSRGraph(num_nodes, offsets, targets, weights)


def _read_problem_line(path: Path) -> tuple[int, int]:
    with path.open("rt", encoding="ascii") as file:
        for line in file:
            if line.startswith("p "):
                fields = line.split()
                if len(fields) != 4 or fields[1] != "sp":
                    raise ValueError(f"unsupported DIMACS problem line: {line.strip()}")
                num_nodes = int(fields[2])
                num_edges = int(fields[3])
                if num_nodes < 0 or num_edges < 0:
                    raise ValueError("DIMACS graph sizes must be non-negative")
                return num_nodes, num_edges
    raise ValueError("missing DIMACS problem line")


def _parse_arc(line: str, num_nodes: int) -> tuple[int, int, int]:
    fields = line.split()
    if len(fields) != 4:
        raise ValueError(f"malformed DIMACS arc line: {line.strip()}")
    source = int(fields[1]) - 1
    target = int(fields[2]) - 1
    weight = int(fields[3])
    if source < 0 or source >= num_nodes or target < 0 or target >= num_nodes:
        raise ValueError(f"DIMACS arc endpoint out of range: {line.strip()}")
    if weight < 0:
        raise ValueError("Dijkstra requires non-negative edge weights")
    return source, target, weight
