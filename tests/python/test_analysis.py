from lapq.analysis import (
    analyze_dijkstra_csvs,
    analyze_queue_insertions_csv,
    main,
    read_dijkstra_csv,
    write_dijkstra_analysis_csv,
    write_queue_insertion_analysis_csv,
)

BASELINE = """\
backend,source,seconds,settled,relaxations,stale_pops,hint_scenario,avg_hint_error,max_hint_error,clean_comparisons
heapq,1,0.25,10,12,2,,0.0,0,
lapq,1,0.50,10,12,2,,0.0,0,100
"""

HINTS = """\
backend,source,seconds,settled,relaxations,stale_pops,hint_scenario,avg_hint_error,max_hint_error,clean_comparisons
lapq,1,0.40,10,12,2,perfect,0.0,0,50
lapq,1,0.60,10,12,2,noisy,3.0,4,150
"""

QUEUE_EVENTS = """\
run,step,source,node,target,distance,edge_weight,queue_size_before,predecessor_rank,predecessor_distance,predecessor_node,predecessor_sequence
0,0,4,4,5,10.0,10,0,-1,,,
0,1,4,4,6,20.0,20,1,0,10.0,5,1
1,0,7,7,8,15.0,15,0,-1,,,
"""


def write_csvs(tmp_path):
    baseline = tmp_path / "baseline.csv"
    hints = tmp_path / "hints.csv"
    baseline.write_text(BASELINE, encoding="utf-8")
    hints.write_text(HINTS, encoding="utf-8")
    return baseline, hints


def test_read_dijkstra_csv(tmp_path):
    baseline, _ = write_csvs(tmp_path)

    rows = read_dijkstra_csv(baseline)

    assert rows[0].backend == "heapq"
    assert rows[0].clean_comparisons is None
    assert rows[1].backend == "lapq"
    assert rows[1].clean_comparisons == 100


def test_analyze_dijkstra_csvs(tmp_path):
    baseline, hints = write_csvs(tmp_path)

    rows = analyze_dijkstra_csvs(baseline, hints)

    assert [row.label for row in rows] == [
        "heapq",
        "lapq",
        "lapq:perfect",
        "lapq:noisy",
    ]
    assert rows[0].speedup_vs_lapq == 2.0
    assert rows[0].comparison_ratio_vs_lapq is None
    assert rows[2].comparison_ratio_vs_lapq == 0.5
    assert rows[2].comparison_reduction_vs_lapq == 0.5
    assert rows[3].avg_hint_error == 3.0


def test_write_dijkstra_analysis_csv_and_cli(tmp_path, capsys):
    baseline, hints = write_csvs(tmp_path)
    output = tmp_path / "summary.csv"

    rows = analyze_dijkstra_csvs(baseline, hints)
    write_dijkstra_analysis_csv(rows, output)

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0] == (
        "label,clean_comparisons,comparison_ratio_vs_lapq,"
        "comparison_reduction_vs_lapq,seconds,avg_hint_error,max_hint_error,"
        "speedup_vs_lapq"
    )
    assert lines[2].startswith("lapq,100,1.0,0.0,0.5,0.0,0,1.0")

    assert main([str(baseline), str(hints), "--csv", str(output)]) == 0
    captured = capsys.readouterr()
    assert "lapq:perfect" in captured.out


def test_analyze_queue_insertions_csv(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text(QUEUE_EVENTS, encoding="utf-8")

    rows = analyze_queue_insertions_csv(path)

    assert len(rows) == 2
    assert rows[0].run == 0
    assert rows[0].source == 4
    assert rows[0].rows == 2
    assert rows[0].avg_distance == 15.0
    assert rows[0].max_queue_size_before == 1
    assert rows[0].predecessor_fraction == 0.5
    assert rows[0].avg_insertion_rank == 0.5
    assert rows[0].avg_tail_gap == 0.0
    assert rows[1].source == 7


def test_write_queue_insertion_analysis_csv_and_cli(tmp_path, capsys):
    path = tmp_path / "events.csv"
    output = tmp_path / "events-analysis.csv"
    path.write_text(QUEUE_EVENTS, encoding="utf-8")

    rows = analyze_queue_insertions_csv(path)
    write_queue_insertion_analysis_csv(rows, output)

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0] == (
        "run,source,rows,min_distance,max_distance,avg_distance,avg_edge_weight,"
        "avg_queue_size_before,max_queue_size_before,predecessor_fraction,"
        "avg_insertion_rank,max_insertion_rank,avg_tail_gap,max_tail_gap"
    )
    assert lines[1].startswith("0,4,2,10.0,20.0,15.0,15.0,")

    assert main(["--queue-events", str(path), "--csv", str(output)]) == 0
    captured = capsys.readouterr()
    assert "total rows: 3" in captured.out
