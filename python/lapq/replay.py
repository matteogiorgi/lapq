"""Replay queue insertion traces with precomputed hints."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from heapq import heappop, heappush
from pathlib import Path
from time import perf_counter
from typing import Literal

from ._lapq import Handle, PriorityQueue

ReplayScenario = Literal["heapq", "baseline", "perfect", "noisy", "bad_left", "rank"]


@dataclass(frozen=True)
class ReplayEvent:
    sequence: int
    key: float
    node: int


@dataclass(frozen=True)
class ReplayPlanItem:
    event: ReplayEvent
    predecessor_sequence: int | None
    rank_hint: int
    error: int


@dataclass(frozen=True)
class ReplayResult:
    scenario: str
    rows: int
    seconds: float
    clean_comparisons: int | None
    predecessor_hints: int
    rank_hints: int
    avg_error: float
    max_error: int
    checksum: int


def read_replay_events(path: str | Path, limit: int | None = None) -> list[ReplayEvent]:
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")

    events: list[ReplayEvent] = []
    with Path(path).open("rt", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            sequence = len(events)
            events.append(
                ReplayEvent(
                    sequence=sequence,
                    key=float(row["distance"]),
                    node=int(row["target"]),
                )
            )
            if limit is not None and len(events) >= limit:
                break
    return events


def run_replay_scenario(
    events: list[ReplayEvent],
    scenario: ReplayScenario,
    noise: int = 64,
) -> ReplayResult:
    if noise < 0:
        raise ValueError("noise must be non-negative")
    if scenario == "heapq":
        return _run_heapq_replay(events)
    if scenario not in {"baseline", "perfect", "noisy", "bad_left", "rank"}:
        raise ValueError(f"unknown replay scenario: {scenario!r}")

    plan = ReplayPlanner(events).build_plan(scenario=scenario, noise=noise)
    return _run_lapq_replay(plan, scenario=scenario)


def _run_lapq_replay(
    plan: list[ReplayPlanItem],
    scenario: ReplayScenario,
) -> ReplayResult:
    queue = PriorityQueue()
    handles: list[Handle | None] = [None] * len(plan)
    checksum = 0
    total_error = 0
    max_error = 0

    start = perf_counter()
    for item in plan:
        event = item.event
        value = (event.sequence, event.node)
        if scenario == "baseline":
            handle = queue.push_handle(event.key, value)
        elif scenario == "rank":
            handle = queue.push_with_rank(event.key, value, item.rank_hint)
        elif item.predecessor_sequence is None:
            handle = queue.push_handle(event.key, value)
        else:
            predecessor = handles[item.predecessor_sequence]
            if predecessor is None:
                raise RuntimeError("replay plan referenced a missing handle")
            handle = queue.push_with_predecessor(event.key, value, predecessor)
        handles[event.sequence] = handle
        total_error += item.error
        max_error = max(max_error, item.error)

    while not queue.empty():
        _, value = queue.pop()
        sequence, node = value
        checksum += int(sequence) ^ int(node)

    seconds = perf_counter() - start
    stats = queue.stats()
    hinted = max(len(plan) - 1, 0) if scenario != "baseline" else 0
    return ReplayResult(
        scenario=scenario,
        rows=len(plan),
        seconds=seconds,
        clean_comparisons=stats["clean_comparisons"],
        predecessor_hints=stats["predecessor_hints"],
        rank_hints=stats["rank_hints"],
        avg_error=total_error / hinted if hinted else 0.0,
        max_error=max_error,
        checksum=checksum,
    )


def build_replay_plan(
    events: list[ReplayEvent],
    scenario: ReplayScenario,
    noise: int = 64,
) -> list[ReplayPlanItem]:
    return ReplayPlanner(events).build_plan(scenario=scenario, noise=noise)


class ReplayPlanner:
    def __init__(self, events: list[ReplayEvent]) -> None:
        indexed = sorted((event.key, event.sequence) for event in events)
        self.events = events
        self.rank_by_sequence = [0] * len(events)
        self.sequence_by_rank = [0] * len(events)
        for rank, (_, sequence) in enumerate(indexed):
            self.rank_by_sequence[sequence] = rank
            self.sequence_by_rank[rank] = sequence

    def build_plan(
        self,
        scenario: ReplayScenario,
        noise: int = 64,
    ) -> list[ReplayPlanItem]:
        if scenario == "heapq":
            raise ValueError("heapq replay does not use a LAPQ hint plan")
        if noise < 0:
            raise ValueError("noise must be non-negative")

        tree = _FenwickTree(len(self.events))
        plan: list[ReplayPlanItem] = []
        for event in self.events:
            plan.append(self._build_item(event, scenario, noise, tree))
            tree.add(self.rank_by_sequence[event.sequence], 1)
        return plan

    def _build_item(
        self,
        event: ReplayEvent,
        scenario: ReplayScenario,
        noise: int,
        tree: "_FenwickTree",
    ) -> ReplayPlanItem:
        rank = self.rank_by_sequence[event.sequence]
        occupied_before = tree.prefix_sum(rank)
        predecessor_sequence: int | None = None
        error = 0

        if scenario in {"perfect", "noisy", "bad_left"} and occupied_before > 0:
            true_order = occupied_before - 1
            if scenario == "perfect":
                predicted_order = true_order
            elif scenario == "noisy":
                predicted_order = max(0, true_order - noise)
            else:
                predicted_order = 0
            predecessor_rank = tree.find_by_order(predicted_order)
            predecessor_sequence = self.sequence_by_rank[predecessor_rank]
            error = true_order - predicted_order

        return ReplayPlanItem(
            event=event,
            predecessor_sequence=predecessor_sequence,
            rank_hint=occupied_before,
            error=error,
        )


def run_replay_scenarios(
    events: list[ReplayEvent],
    scenarios: tuple[ReplayScenario, ...],
    noise: int = 64,
) -> list[ReplayResult]:
    planner = ReplayPlanner(events)
    rows: list[ReplayResult] = []
    for scenario in scenarios:
        if scenario == "heapq":
            rows.append(_run_heapq_replay(events))
        else:
            rows.append(
                _run_lapq_replay(
                    planner.build_plan(scenario=scenario, noise=noise),
                    scenario=scenario,
                )
            )
    return rows


def write_replay_results_csv(rows: list[ReplayResult], path: str | Path) -> None:
    baseline = _find_comparison_baseline(rows)
    with Path(path).open("wt", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "scenario",
                "rows",
                "clean_comparisons",
                "comparison_ratio_vs_baseline",
                "comparison_reduction_vs_baseline",
                "predecessor_hints",
                "rank_hints",
                "avg_error",
                "max_error",
                "seconds",
                "checksum",
            ]
        )
        for row in rows:
            ratio = _comparison_ratio(row.clean_comparisons, baseline)
            writer.writerow(
                [
                    row.scenario,
                    row.rows,
                    "" if row.clean_comparisons is None else row.clean_comparisons,
                    "" if ratio is None else ratio,
                    "" if ratio is None else 1.0 - ratio,
                    row.predecessor_hints,
                    row.rank_hints,
                    row.avg_error,
                    row.max_error,
                    row.seconds,
                    row.checksum,
                ]
            )


def print_replay_results(rows: list[ReplayResult]) -> None:
    baseline = _find_comparison_baseline(rows)
    header = (
        f"{'scenario':<12} {'rows':>8} {'clean_cmp':>12} "
        f"{'cmp_ratio':>10} {'cmp_saved':>10} {'pred':>8} {'rank':>8} "
        f"{'avg_err':>10} {'max_err':>8} {'seconds':>10}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        clean = "-" if row.clean_comparisons is None else str(row.clean_comparisons)
        ratio = _comparison_ratio(row.clean_comparisons, baseline)
        ratio_text = "-" if ratio is None else f"{ratio:.3f}"
        saved_text = "-" if ratio is None else f"{100.0 * (1.0 - ratio):.2f}%"
        print(
            f"{row.scenario:<12} {row.rows:>8} {clean:>12} "
            f"{ratio_text:>10} {saved_text:>10} "
            f"{row.predecessor_hints:>8} {row.rank_hints:>8} "
            f"{row.avg_error:>10.3f} {row.max_error:>8} "
            f"{row.seconds:>10.6f}"
        )


def _run_heapq_replay(events: list[ReplayEvent]) -> ReplayResult:
    heap: list[tuple[float, int, int]] = []
    checksum = 0
    start = perf_counter()
    for event in events:
        heappush(heap, (event.key, event.sequence, event.node))
    while heap:
        _, sequence, node = heappop(heap)
        checksum += int(sequence) ^ int(node)
    return ReplayResult(
        scenario="heapq",
        rows=len(events),
        seconds=perf_counter() - start,
        clean_comparisons=None,
        predecessor_hints=0,
        rank_hints=0,
        avg_error=0.0,
        max_error=0,
        checksum=checksum,
    )


def _find_comparison_baseline(rows: list[ReplayResult]) -> int | None:
    for row in rows:
        if row.scenario == "baseline":
            return row.clean_comparisons
    for row in rows:
        if row.clean_comparisons is not None:
            return row.clean_comparisons
    return None


def _comparison_ratio(value: int | None, baseline: int | None) -> float | None:
    if value is None or baseline is None or baseline == 0:
        return None
    return value / baseline


class _FenwickTree:
    def __init__(self, size: int) -> None:
        self.values = [0] * (size + 1)

    def add(self, index: int, delta: int) -> None:
        index += 1
        while index < len(self.values):
            self.values[index] += delta
            index += index & -index

    def prefix_sum(self, end: int) -> int:
        total = 0
        while end > 0:
            total += self.values[end]
            end -= end & -end
        return total

    def find_by_order(self, order: int) -> int:
        index = 0
        bit = 1 << (len(self.values).bit_length() - 1)
        remaining = order + 1
        while bit:
            next_index = index + bit
            if next_index < len(self.values) and self.values[next_index] < remaining:
                index = next_index
                remaining -= self.values[next_index]
            bit >>= 1
        return index


def _parse_scenarios(value: str) -> tuple[ReplayScenario, ...]:
    if value == "all":
        return ("heapq", "baseline", "perfect", "noisy", "bad_left")
    scenarios = tuple(part.strip() for part in value.split(",") if part.strip())
    valid = {"heapq", "baseline", "perfect", "noisy", "bad_left", "rank"}
    for scenario in scenarios:
        if scenario not in valid:
            raise SystemExit(f"unknown replay scenario: {scenario}")
    if not scenarios:
        raise SystemExit("--scenario must contain at least one scenario")
    return scenarios  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay queue insertion events with precomputed hints."
    )
    parser.add_argument("events_csv", help="CSV produced by lapq.datasets")
    parser.add_argument(
        "--scenario",
        default="all",
        help="all or comma-separated replay scenarios; rank is opt-in",
    )
    parser.add_argument("--noise", type=int, default=64, help="noisy hint distance")
    parser.add_argument(
        "--limit", type=int, default=None, help="maximum events to read"
    )
    parser.add_argument("--csv", help="optional CSV output path")
    args = parser.parse_args(argv)
    if args.noise < 0:
        parser.error("--noise must be non-negative")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")

    events = read_replay_events(args.events_csv, limit=args.limit)
    rows = run_replay_scenarios(
        events,
        scenarios=_parse_scenarios(args.scenario),
        noise=args.noise,
    )
    print_replay_results(rows)
    if args.csv is not None:
        write_replay_results_csv(rows, args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
