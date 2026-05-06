from lapq.replay import (
    build_replay_plan,
    main,
    read_replay_events,
    run_replay_scenario,
    run_replay_scenarios,
    write_replay_results_csv,
)

EVENTS = """\
run,step,source,node,target,distance,edge_weight,queue_size_before,predecessor_rank,predecessor_distance,predecessor_node,predecessor_sequence
0,0,1,1,10,5.0,5,0,-1,,,
0,1,1,1,11,2.0,2,1,-1,,,
0,2,1,1,12,8.0,8,2,0,5.0,10,0
0,3,1,1,13,6.0,6,3,1,5.0,10,0
"""


def write_events(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text(EVENTS, encoding="utf-8")
    return path


def test_read_replay_events_and_plan(tmp_path):
    events = read_replay_events(write_events(tmp_path))

    assert [event.key for event in events] == [5.0, 2.0, 8.0, 6.0]
    assert [event.node for event in events] == [10, 11, 12, 13]

    perfect = build_replay_plan(events, scenario="perfect")
    noisy = build_replay_plan(events, scenario="noisy", noise=1)

    assert [item.predecessor_sequence for item in perfect] == [None, None, 0, 0]
    assert [item.rank_hint for item in perfect] == [0, 0, 2, 2]
    assert [item.error for item in perfect] == [0, 0, 0, 0]
    assert [item.predecessor_sequence for item in noisy] == [None, None, 1, 1]
    assert [item.error for item in noisy] == [0, 0, 1, 1]


def test_run_replay_scenarios(tmp_path):
    events = read_replay_events(write_events(tmp_path))

    heapq = run_replay_scenario(events, "heapq")
    baseline = run_replay_scenario(events, "baseline")
    perfect = run_replay_scenario(events, "perfect")
    rows = run_replay_scenarios(events, ("baseline", "perfect", "rank"))

    assert heapq.clean_comparisons is None
    assert baseline.clean_comparisons is not None
    assert baseline.predecessor_hints == 0
    assert perfect.predecessor_hints == 2
    assert perfect.avg_error == 0.0
    assert [row.scenario for row in rows] == ["baseline", "perfect", "rank"]


def test_write_replay_results_csv_and_cli(tmp_path, capsys):
    events_path = write_events(tmp_path)
    output = tmp_path / "replay.csv"
    rows = run_replay_scenarios(
        read_replay_events(events_path),
        ("heapq", "baseline", "perfect"),
    )

    write_replay_results_csv(rows, output)

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0] == (
        "scenario,rows,clean_comparisons,comparison_ratio_vs_baseline,"
        "comparison_reduction_vs_baseline,predecessor_hints,rank_hints,"
        "avg_error,max_error,seconds,checksum"
    )
    assert lines[1].startswith("heapq,4,")

    assert (
        main(
            [
                str(events_path),
                "--scenario",
                "baseline,perfect",
                "--csv",
                str(output),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert "perfect" in captured.out


def test_replay_cli_all_excludes_rank_by_default(tmp_path, capsys):
    events_path = write_events(tmp_path)

    assert main([str(events_path), "--scenario", "all"]) == 0

    captured = capsys.readouterr()
    assert "bad_left" in captured.out
    scenarios = [line.split()[0] for line in captured.out.splitlines()[2:]]
    assert "rank" not in scenarios
