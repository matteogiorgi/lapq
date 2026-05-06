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
    seconds: float
    clean_comparisons: int | None
    avg_hint_error: float
    max_hint_error: int
    speedup_vs_lapq: float | None
    comparison_ratio_vs_lapq: float | None


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
        analyzed.append(
            DijkstraAnalysisRow(
                label=label,
                seconds=row.seconds,
                clean_comparisons=row.clean_comparisons,
                avg_hint_error=row.avg_hint_error,
                max_hint_error=row.max_hint_error,
                speedup_vs_lapq=(
                    lapq_baseline.seconds / row.seconds if row.seconds > 0 else None
                ),
                comparison_ratio_vs_lapq=_comparison_ratio(
                    row.clean_comparisons,
                    lapq_baseline.clean_comparisons,
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
                "seconds",
                "clean_comparisons",
                "avg_hint_error",
                "max_hint_error",
                "speedup_vs_lapq",
                "comparison_ratio_vs_lapq",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.label,
                    row.seconds,
                    "" if row.clean_comparisons is None else row.clean_comparisons,
                    row.avg_hint_error,
                    row.max_hint_error,
                    "" if row.speedup_vs_lapq is None else row.speedup_vs_lapq,
                    (
                        ""
                        if row.comparison_ratio_vs_lapq is None
                        else row.comparison_ratio_vs_lapq
                    ),
                ]
            )


def print_dijkstra_analysis(rows: list[DijkstraAnalysisRow]) -> None:
    header = (
        f"{'scenario':<18} {'seconds':>10} {'clean_cmp':>12} "
        f"{'avg_err':>10} {'max_err':>8} {'speedup':>9} {'cmp_ratio':>10}"
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
        print(
            f"{row.label:<18} {row.seconds:>10.6f} {clean:>12} "
            f"{row.avg_hint_error:>10.3f} {row.max_hint_error:>8} "
            f"{speedup:>9} {ratio:>10}"
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
        "baseline_csv", help="CSV produced by lapq.dijkstra --backend both"
    )
    parser.add_argument(
        "hints_csv", help="CSV produced by lapq.dijkstra --backend lapq-hints"
    )
    parser.add_argument("--csv", help="optional CSV summary output path")
    args = parser.parse_args(argv)

    rows = analyze_dijkstra_csvs(args.baseline_csv, args.hints_csv)
    print_dijkstra_analysis(rows)
    if args.csv is not None:
        write_dijkstra_analysis_csv(rows, args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
