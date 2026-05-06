from math import inf

import pytest

from lapq.datasets import (
    build_priority_queue_dataset_csv,
    build_priority_queue_dataset_multi_source_csv,
    build_relaxation_dataset_csv,
    build_relaxation_dataset_multi_source_csv,
    choose_random_sources,
    collect_priority_queue_insertion_events,
    collect_relaxation_events,
    write_priority_queue_insertion_events_csv,
    write_relaxation_events_csv,
)
from lapq.dijkstra import (
    benchmark_dijkstra_backends,
    benchmark_dijkstra_hint_scenarios,
    dijkstra,
    dijkstra_heapq,
    dijkstra_lapq_hinted,
    dijkstra_lapq,
    write_dijkstra_benchmark_csv,
)
from lapq.datasets import main as datasets_main
from lapq.dijkstra import main as dijkstra_main
from lapq.graph import load_dimacs_csr


DIMACS_GRAPH = """\
c small shortest-path graph
p sp 5 7
a 1 2 2
a 1 3 5
a 2 3 1
a 2 4 2
a 3 4 1
a 4 5 3
a 2 5 10
"""


def write_dimacs(tmp_path):
    path = tmp_path / "small.gr"
    path.write_text(DIMACS_GRAPH, encoding="ascii")
    return path


def test_load_dimacs_csr(tmp_path):
    graph = load_dimacs_csr(write_dimacs(tmp_path))

    assert graph.num_nodes == 5
    assert graph.num_edges == 7
    assert graph.out_degree(0) == 2
    assert list(graph.neighbors(0)) == [(1, 2), (2, 5)]
    assert list(graph.neighbors(4)) == []
    with pytest.raises(IndexError):
        list(graph.neighbors(5))


def test_dijkstra_heapq_and_lapq_agree(tmp_path):
    graph = load_dimacs_csr(write_dimacs(tmp_path))

    heapq_result = dijkstra_heapq(graph, 0)
    lapq_result = dijkstra_lapq(graph, 0)

    assert list(heapq_result.distances) == [0.0, 2.0, 3.0, 4.0, 7.0]
    assert list(lapq_result.distances) == list(heapq_result.distances)
    assert heapq_result.relaxations == 6
    assert lapq_result.relaxations == 6
    assert lapq_result.queue_stats is not None
    assert lapq_result.queue_stats["clean_comparisons"] > 0


def test_dijkstra_dispatch_and_unreachable_nodes(tmp_path):
    graph = load_dimacs_csr(write_dimacs(tmp_path))

    result = dijkstra(graph, 4, backend="heapq")

    assert result.distances[4] == 0.0
    assert result.distances[0] == inf
    with pytest.raises(ValueError):
        dijkstra(graph, 0, backend="unknown")


def test_collect_relaxation_events(tmp_path):
    graph = load_dimacs_csr(write_dimacs(tmp_path))

    events = collect_relaxation_events(graph, 0, max_events=3)

    assert len(events) == 3
    assert events[0].source == 0
    assert events[0].node == 0
    assert events[0].target == 1
    assert events[0].run == 0
    assert events[0].old_distance == inf
    assert events[0].new_distance == 2.0
    assert events[0].edge_weight == 2
    assert events[0].queue_size == 1


def test_write_relaxation_events_csv(tmp_path):
    graph_path = write_dimacs(tmp_path)
    graph = load_dimacs_csr(graph_path)
    output = tmp_path / "events.csv"

    rows = write_relaxation_events_csv(
        collect_relaxation_events(graph, 0, max_events=2),
        output,
    )

    assert rows == 2
    assert output.read_text(encoding="utf-8").splitlines() == [
        "run,step,source,node,target,old_distance,new_distance,edge_weight,queue_size",
        "0,0,0,0,1,inf,2.0,2,1",
        "0,1,0,0,2,inf,5.0,5,2",
    ]


def test_build_relaxation_dataset_csv_and_cli(tmp_path):
    graph_path = write_dimacs(tmp_path)
    output = tmp_path / "dataset.csv"

    rows = build_relaxation_dataset_csv(graph_path, output, source=0, max_events=1)
    assert rows == 1
    assert output.read_text(encoding="utf-8").splitlines()[1] == "0,0,0,0,1,inf,2.0,2,1"

    cli_output = tmp_path / "dataset-cli.csv"
    assert datasets_main(
        [
            str(graph_path),
            str(cli_output),
            "--kind",
            "relaxations",
            "--source",
            "1",
            "--max-events",
            "1",
        ]
    ) == 0
    assert cli_output.read_text(encoding="utf-8").splitlines()[1] == "0,0,0,0,1,inf,2.0,2,1"


def test_priority_queue_insertion_events_and_csv(tmp_path):
    graph_path = write_dimacs(tmp_path)
    graph = load_dimacs_csr(graph_path)
    output = tmp_path / "queue-events.csv"

    events = collect_priority_queue_insertion_events(graph, 0, max_events=3)

    assert len(events) == 3
    assert events[0].target == 1
    assert events[0].run == 0
    assert events[0].distance == 2.0
    assert events[0].queue_size_before == 0
    assert events[0].predecessor_rank == -1
    assert events[0].predecessor_node is None
    assert events[1].target == 2
    assert events[1].predecessor_rank == 0
    assert events[1].predecessor_node == 1

    rows = write_priority_queue_insertion_events_csv(events, output)
    lines = output.read_text(encoding="utf-8").splitlines()
    assert rows == 3
    assert lines[0] == (
        "run,step,source,node,target,distance,edge_weight,queue_size_before,"
        "predecessor_rank,predecessor_distance,predecessor_node,"
        "predecessor_sequence"
    )
    assert lines[1] == "0,0,0,0,1,2.0,2,0,-1,,,"

    built = tmp_path / "queue-built.csv"
    assert build_priority_queue_dataset_csv(graph_path, built, source=0, max_events=1) == 1
    assert built.read_text(encoding="utf-8").splitlines()[1] == "0,0,0,0,1,2.0,2,0,-1,,,"


def test_multi_source_dataset_generation(tmp_path):
    graph_path = write_dimacs(tmp_path)
    graph = load_dimacs_csr(graph_path)
    queue_output = tmp_path / "queue-multi.csv"
    relaxation_output = tmp_path / "relax-multi.csv"

    assert choose_random_sources(graph, count=3, seed=123) == [0, 2, 4]
    queue_rows = build_priority_queue_dataset_multi_source_csv(
        graph_path,
        queue_output,
        sources=[0, 1],
        max_events_per_source=1,
    )
    relaxation_rows = build_relaxation_dataset_multi_source_csv(
        graph_path,
        relaxation_output,
        sources=[0, 1],
        max_events_per_source=1,
    )

    queue_lines = queue_output.read_text(encoding="utf-8").splitlines()
    relaxation_lines = relaxation_output.read_text(encoding="utf-8").splitlines()
    assert queue_rows == 2
    assert relaxation_rows == 2
    assert queue_lines[1].startswith("0,0,0,0,1,")
    assert queue_lines[2].startswith("1,0,1,1,2,")
    assert relaxation_lines[1].startswith("0,0,0,0,1,")
    assert relaxation_lines[2].startswith("1,0,1,1,2,")


def test_dataset_cli_multi_source_modes(tmp_path):
    graph_path = write_dimacs(tmp_path)
    manual_output = tmp_path / "manual.csv"
    sampled_output = tmp_path / "sampled.csv"

    assert datasets_main(
        [
            str(graph_path),
            str(manual_output),
            "--sources",
            "1,2",
            "--max-events-per-source",
            "1",
        ]
    ) == 0
    assert datasets_main(
        [
            str(graph_path),
            str(sampled_output),
            "--source-count",
            "2",
            "--source-seed",
            "123",
            "--max-events-per-source",
            "1",
        ]
    ) == 0

    assert len(manual_output.read_text(encoding="utf-8").splitlines()) == 3
    assert len(sampled_output.read_text(encoding="utf-8").splitlines()) == 3


def test_benchmark_dijkstra_backends_and_csv(tmp_path):
    graph = load_dimacs_csr(write_dimacs(tmp_path))
    rows = benchmark_dijkstra_backends(graph, 0)
    output = tmp_path / "bench.csv"

    assert [row.backend for row in rows] == ["heapq", "lapq"]
    assert rows[0].source == 0
    assert rows[0].settled == 5
    assert rows[1].clean_comparisons is not None

    write_dijkstra_benchmark_csv(rows, output)
    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0] == (
        "backend,source,seconds,settled,relaxations,stale_pops,"
        "hint_scenario,avg_hint_error,max_hint_error,clean_comparisons"
    )
    assert lines[1].startswith("heapq,1,")
    assert lines[2].startswith("lapq,1,")


def test_dijkstra_hinted_scenarios(tmp_path):
    graph = load_dimacs_csr(write_dimacs(tmp_path))

    baseline = dijkstra_lapq_hinted(graph, 0, scenario="baseline")
    perfect = dijkstra_lapq_hinted(graph, 0, scenario="perfect")
    noisy = dijkstra_lapq_hinted(graph, 0, scenario="noisy", noise=1)
    rows = benchmark_dijkstra_hint_scenarios(
        graph,
        0,
        scenarios=("baseline", "perfect", "noisy", "rank"),
        noise=1,
    )

    assert list(baseline.distances) == [0.0, 2.0, 3.0, 4.0, 7.0]
    assert list(perfect.distances) == list(baseline.distances)
    assert list(noisy.distances) == list(baseline.distances)
    assert perfect.queue_stats is not None
    assert perfect.queue_stats["predecessor_hints"] > 0
    assert noisy.max_hint_error <= 1
    assert [row.hint_scenario for row in rows] == ["baseline", "perfect", "noisy", "rank"]


def test_dijkstra_cli(tmp_path, capsys):
    graph_path = write_dimacs(tmp_path)
    output = tmp_path / "dijkstra.csv"

    assert dijkstra_main([str(graph_path), "--source", "1", "--backend", "heapq", "--csv", str(output)]) == 0
    captured = capsys.readouterr()

    assert (
        "backend,source,seconds,settled,relaxations,stale_pops,"
        "hint_scenario,avg_hint_error,max_hint_error,clean_comparisons"
    ) in captured.out
    assert "heapq,1," in captured.out
    assert output.read_text(encoding="utf-8").splitlines()[1].startswith("heapq,1,")

    assert dijkstra_main(
        [
            str(graph_path),
            "--source",
            "1",
            "--backend",
            "lapq-hints",
            "--hint-scenario",
            "perfect",
        ]
    ) == 0
