from lapq.analysis import (
    analyze_dijkstra_csvs,
    main,
    read_dijkstra_csv,
    write_dijkstra_analysis_csv,
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

    assert [row.label for row in rows] == ["heapq", "lapq", "lapq:perfect", "lapq:noisy"]
    assert rows[0].speedup_vs_lapq == 2.0
    assert rows[0].comparison_ratio_vs_lapq is None
    assert rows[2].comparison_ratio_vs_lapq == 0.5
    assert rows[3].avg_hint_error == 3.0


def test_write_dijkstra_analysis_csv_and_cli(tmp_path, capsys):
    baseline, hints = write_csvs(tmp_path)
    output = tmp_path / "summary.csv"

    rows = analyze_dijkstra_csvs(baseline, hints)
    write_dijkstra_analysis_csv(rows, output)

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0] == (
        "label,seconds,clean_comparisons,avg_hint_error,max_hint_error,"
        "speedup_vs_lapq,comparison_ratio_vs_lapq"
    )
    assert lines[2].startswith("lapq,0.5,100,")

    assert main([str(baseline), str(hints), "--csv", str(output)]) == 0
    captured = capsys.readouterr()
    assert "lapq:perfect" in captured.out
