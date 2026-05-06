import pytest

from lapq import Handle, PriorityQueue, run_insertion_scenario


def test_push_pop_order():
    queue = PriorityQueue()

    queue.push(3.0, "c")
    queue.push(1.0, "a")
    queue.push(2.0, "b")

    assert len(queue) == 3
    assert queue.peek() == (1.0, "a")
    assert queue.pop() == (1.0, "a")
    assert queue.pop() == (2.0, "b")
    assert queue.pop() == (3.0, "c")
    assert queue.empty()


def test_equal_priorities_are_stable():
    queue = PriorityQueue()

    queue.push(1.0, "first")
    queue.push(1.0, "second")

    assert queue.pop() == (1.0, "first")
    assert queue.pop() == (1.0, "second")


def test_clear_and_stats():
    queue = PriorityQueue()

    for key in [5.0, 2.0, 4.0, 1.0]:
        queue.push(key, key)
    assert len(queue) == 4
    assert queue.stats()["clean_comparisons"] > 0
    queue.reset_stats()
    assert queue.stats()["clean_comparisons"] == 0
    queue.clear()
    assert len(queue) == 0
    assert queue.check_invariants()


def test_constructor_config_can_disable_stats():
    queue = PriorityQueue(seed=123, stats=False)

    queue.push(2.0, "b")
    queue.push(1.0, "a")

    assert queue.pop() == (1.0, "a")
    assert queue.stats()["clean_comparisons"] == 0
    assert queue.check_invariants()


def test_predecessor_hint_handles():
    queue = PriorityQueue()

    first = queue.push_handle(1.0, "a")
    assert isinstance(first, Handle)
    second = queue.push_with_predecessor(2.0, "b", first)
    third = queue.push_with_predecessor(3.0, "c", second)

    assert isinstance(third, Handle)
    stats = queue.stats()
    assert stats["predecessor_hints"] == 2
    assert stats["invalid_hints"] == 0
    assert queue.pop() == (1.0, "a")
    assert queue.pop() == (2.0, "b")
    assert queue.pop() == (3.0, "c")


def test_remove_by_handle():
    queue = PriorityQueue()

    first = queue.push_handle(1.0, "a")
    second = queue.push_handle(2.0, "b")
    third = queue.push_handle(3.0, "c")

    assert queue.remove(second) == (2.0, "b")
    assert len(queue) == 2
    assert queue.check_invariants()
    with pytest.raises(KeyError):
        queue.remove(second)
    assert queue.pop() == (1.0, "a")
    assert queue.pop() == (3.0, "c")
    assert isinstance(first, Handle)
    assert isinstance(third, Handle)


def test_rank_hint_handles():
    queue = PriorityQueue()

    queue.push(2.0, "b")
    handle = queue.push_with_rank(1.0, "a", 0)

    assert isinstance(handle, Handle)
    assert queue.stats()["rank_hints"] == 1
    assert queue.pop() == (1.0, "a")
    assert queue.pop() == (2.0, "b")


def test_hint_argument_validation():
    queue = PriorityQueue()

    with pytest.raises(TypeError):
        queue.push_with_predecessor(1.0, "a", object())
    with pytest.raises(ValueError):
        queue.push_with_rank(1.0, "a", -1)


def test_synthetic_insertion_experiments():
    baseline = run_insertion_scenario(16, "baseline")
    perfect = run_insertion_scenario(16, "perfect")
    noisy = run_insertion_scenario(16, "noisy", noise=3)

    assert baseline.checksum == sum(range(16))
    assert perfect.checksum == sum(range(16))
    assert noisy.checksum == sum(range(16))
    assert baseline.stats["predecessor_hints"] == 0
    assert perfect.stats["predecessor_hints"] == 15
    assert perfect.avg_error == 0.0
    assert noisy.stats["predecessor_hints"] == 15
    assert noisy.max_error == 3
