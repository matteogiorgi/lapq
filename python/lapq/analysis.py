"""Minimal CSV analysis helpers for LAPQ experiments."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DijkstraCsvRow:
    backend: str
    source: int
    seconds: float
    settled: int
    relaxations: int
    stale_pops: int
    hint_scenario: str
    avg_hint_error: float
    max_hint_error: int
    clean_comparisons: int | None


@dataclass(frozen=True)
class DijkstraAnalysisRow:
    label: str
    clean_comparisons: int | None
    comparison_ratio_vs_lapq: float | None
    comparison_reduction_vs_lapq: float | None
    seconds: float
    avg_hint_error: float
    max_hint_error: int
    speedup_vs_lapq: float | None


@dataclass(frozen=True)
class QueueInsertionAnalysisRow:
    run: int
    source: int
    rows: int
    min_distance: float
    max_distance: float
    avg_distance: float
    avg_edge_weight: float
    avg_queue_size_before: float
    max_queue_size_before: int
    predecessor_fraction: float
    avg_insertion_rank: float
    max_insertion_rank: int
    avg_tail_gap: float
    max_tail_gap: int


def read_dijkstra_csv(path: str | Path) -> list[DijkstraCsvRow]:
    rows: list[DijkstraCsvRow] = []
    with Path(path).open("rt", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            rows.append(
                DijkstraCsvRow(
                    backend=row["backend"],
                    source=int(row["source"]),
                    seconds=float(row["seconds"]),
                    settled=int(row["settled"]),
                    relaxations=int(row["relaxations"]),
                    stale_pops=int(row["stale_pops"]),
                    hint_scenario=row.get("hint_scenario", ""),
                    avg_hint_error=float(row.get("avg_hint_error") or 0.0),
                    max_hint_error=int(row.get("max_hint_error") or 0),
                    clean_comparisons=_optional_int(row.get("clean_comparisons")),
                )
            )
    return rows


def analyze_queue_insertions_csv(path: str | Path) -> list[QueueInsertionAnalysisRow]:
    builders: dict[int, _QueueInsertionRunBuilder] = {}
    with Path(path).open("rt", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            run = int(row["run"])
            builder = builders.get(run)
            if builder is None:
                builder = _QueueInsertionRunBuilder(
                    run=run,
                    source=int(row["source"]),
                )
                builders[run] = builder
            builder.add(row)
    return [builders[run].finish() for run in sorted(builders)]


def analyze_dijkstra_csvs(
    baseline_path: str | Path,
    hints_path: str | Path,
) -> list[DijkstraAnalysisRow]:
    baseline = read_dijkstra_csv(baseline_path)
    hints = read_dijkstra_csv(hints_path)
    lapq_baseline = _find_lapq_baseline(baseline)
    analyzed: list[DijkstraAnalysisRow] = []

    for row in [*baseline, *hints]:
        label = (
            row.backend
            if not row.hint_scenario
            else f"{row.backend}:{row.hint_scenario}"
        )
        comparison_ratio = _comparison_ratio(
            row.clean_comparisons,
            lapq_baseline.clean_comparisons,
        )
        analyzed.append(
            DijkstraAnalysisRow(
                label=label,
                clean_comparisons=row.clean_comparisons,
                comparison_ratio_vs_lapq=comparison_ratio,
                comparison_reduction_vs_lapq=(
                    None if comparison_ratio is None else 1.0 - comparison_ratio
                ),
                seconds=row.seconds,
                avg_hint_error=row.avg_hint_error,
                max_hint_error=row.max_hint_error,
                speedup_vs_lapq=(
                    lapq_baseline.seconds / row.seconds if row.seconds > 0 else None
                ),
            )
        )
    return analyzed


def write_dijkstra_analysis_csv(
    rows: list[DijkstraAnalysisRow],
    path: str | Path,
) -> None:
    with Path(path).open("wt", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "label",
                "clean_comparisons",
                "comparison_ratio_vs_lapq",
                "comparison_reduction_vs_lapq",
                "seconds",
                "avg_hint_error",
                "max_hint_error",
                "speedup_vs_lapq",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.label,
                    "" if row.clean_comparisons is None else row.clean_comparisons,
                    (
                        ""
                        if row.comparison_ratio_vs_lapq is None
                        else row.comparison_ratio_vs_lapq
                    ),
                    (
                        ""
                        if row.comparison_reduction_vs_lapq is None
                        else row.comparison_reduction_vs_lapq
                    ),
                    row.seconds,
                    row.avg_hint_error,
                    row.max_hint_error,
                    "" if row.speedup_vs_lapq is None else row.speedup_vs_lapq,
                ]
            )


def write_queue_insertion_analysis_csv(
    rows: list[QueueInsertionAnalysisRow],
    path: str | Path,
) -> None:
    with Path(path).open("wt", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "run",
                "source",
                "rows",
                "min_distance",
                "max_distance",
                "avg_distance",
                "avg_edge_weight",
                "avg_queue_size_before",
                "max_queue_size_before",
                "predecessor_fraction",
                "avg_insertion_rank",
                "max_insertion_rank",
                "avg_tail_gap",
                "max_tail_gap",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.run,
                    row.source,
                    row.rows,
                    row.min_distance,
                    row.max_distance,
                    row.avg_distance,
                    row.avg_edge_weight,
                    row.avg_queue_size_before,
                    row.max_queue_size_before,
                    row.predecessor_fraction,
                    row.avg_insertion_rank,
                    row.max_insertion_rank,
                    row.avg_tail_gap,
                    row.max_tail_gap,
                ]
            )


def print_dijkstra_analysis(rows: list[DijkstraAnalysisRow]) -> None:
    header = (
        f"{'scenario':<18} {'clean_cmp':>12} {'cmp_ratio':>10} "
        f"{'cmp_saved':>10} {'avg_err':>10} {'max_err':>8} "
        f"{'seconds':>10} {'speedup':>9}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        clean = "-" if row.clean_comparisons is None else str(row.clean_comparisons)
        speedup = "-" if row.speedup_vs_lapq is None else f"{row.speedup_vs_lapq:.3f}"
        ratio = (
            "-"
            if row.comparison_ratio_vs_lapq is None
            else f"{row.comparison_ratio_vs_lapq:.3f}"
        )
        saved = (
            "-"
            if row.comparison_reduction_vs_lapq is None
            else f"{100.0 * row.comparison_reduction_vs_lapq:.2f}%"
        )
        print(
            f"{row.label:<18} {clean:>12} {ratio:>10} {saved:>10} "
            f"{row.avg_hint_error:>10.3f} {row.max_hint_error:>8} "
            f"{row.seconds:>10.6f} {speedup:>9}"
        )


def print_queue_insertion_analysis(rows: list[QueueInsertionAnalysisRow]) -> None:
    header = (
        f"{'run':>3} {'source':>8} {'rows':>8} {'avg_dist':>12} "
        f"{'max_dist':>12} {'avg_q':>10} {'max_q':>7} {'pred%':>8} "
        f"{'avg_rank':>10} {'avg_tail':>10}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row.run:>3} {row.source:>8} {row.rows:>8} "
            f"{row.avg_distance:>12.3f} {row.max_distance:>12.3f} "
            f"{row.avg_queue_size_before:>10.3f} "
            f"{row.max_queue_size_before:>7} "
            f"{100.0 * row.predecessor_fraction:>7.2f}% "
            f"{row.avg_insertion_rank:>10.3f} {row.avg_tail_gap:>10.3f}"
        )
    if rows:
        total_rows = sum(row.rows for row in rows)
        print(f"\ntotal rows: {total_rows}")


class _QueueInsertionRunBuilder:
    def __init__(self, run: int, source: int) -> None:
        self.run = run
        self.source = source
        self.rows = 0
        self.min_distance = float("inf")
        self.max_distance = float("-inf")
        self.distance_sum = 0.0
        self.edge_weight_sum = 0.0
        self.queue_size_sum = 0
        self.max_queue_size = 0
        self.predecessor_count = 0
        self.insertion_rank_sum = 0
        self.max_insertion_rank = 0
        self.tail_gap_sum = 0
        self.max_tail_gap = 0

    def add(self, row: dict[str, str]) -> None:
        distance = float(row["distance"])
        edge_weight = int(row["edge_weight"])
        queue_size = int(row["queue_size_before"])
        predecessor_rank = int(row["predecessor_rank"])
        insertion_rank = predecessor_rank + 1
        tail_gap = queue_size - insertion_rank

        self.rows += 1
        self.min_distance = min(self.min_distance, distance)
        self.max_distance = max(self.max_distance, distance)
        self.distance_sum += distance
        self.edge_weight_sum += edge_weight
        self.queue_size_sum += queue_size
        self.max_queue_size = max(self.max_queue_size, queue_size)
        if predecessor_rank >= 0:
            self.predecessor_count += 1
        self.insertion_rank_sum += insertion_rank
        self.max_insertion_rank = max(self.max_insertion_rank, insertion_rank)
        self.tail_gap_sum += tail_gap
        self.max_tail_gap = max(self.max_tail_gap, tail_gap)

    def finish(self) -> QueueInsertionAnalysisRow:
        if self.rows == 0:
            raise ValueError("cannot summarize an empty run")
        return QueueInsertionAnalysisRow(
            run=self.run,
            source=self.source,
            rows=self.rows,
            min_distance=self.min_distance,
            max_distance=self.max_distance,
            avg_distance=self.distance_sum / self.rows,
            avg_edge_weight=self.edge_weight_sum / self.rows,
            avg_queue_size_before=self.queue_size_sum / self.rows,
            max_queue_size_before=self.max_queue_size,
            predecessor_fraction=self.predecessor_count / self.rows,
            avg_insertion_rank=self.insertion_rank_sum / self.rows,
            max_insertion_rank=self.max_insertion_rank,
            avg_tail_gap=self.tail_gap_sum / self.rows,
            max_tail_gap=self.max_tail_gap,
        )


def _find_lapq_baseline(rows: list[DijkstraCsvRow]) -> DijkstraCsvRow:
    for row in rows:
        if row.backend == "lapq" and row.hint_scenario == "":
            if row.clean_comparisons is None:
                raise ValueError("LAPQ baseline row has no clean comparisons")
            return row
    raise ValueError("missing LAPQ baseline row")


def _comparison_ratio(value: int | None, baseline: int | None) -> float | None:
    if value is None or baseline is None or baseline == 0:
        return None
    return value / baseline


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze LAPQ Dijkstra CSV outputs.")
    parser.add_argument(
        "baseline_csv",
        nargs="?",
        help="CSV produced by lapq.dijkstra --backend both",
    )
    parser.add_argument(
        "hints_csv",
        nargs="?",
        help="CSV produced by lapq.dijkstra --backend lapq-hints",
    )
    parser.add_argument(
        "--queue-events",
        help="CSV produced by lapq.datasets --kind queue-insertions",
    )
    parser.add_argument("--csv", help="optional CSV summary output path")
    args = parser.parse_args(argv)

    if args.queue_events is not None:
        rows = analyze_queue_insertions_csv(args.queue_events)
        print_queue_insertion_analysis(rows)
        if args.csv is not None:
            write_queue_insertion_analysis_csv(rows, args.csv)
        return 0

    if args.baseline_csv is None or args.hints_csv is None:
        parser.error("baseline_csv and hints_csv are required without --queue-events")

    rows = analyze_dijkstra_csvs(args.baseline_csv, args.hints_csv)
    print_dijkstra_analysis(rows)
    if args.csv is not None:
        write_dijkstra_analysis_csv(rows, args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
