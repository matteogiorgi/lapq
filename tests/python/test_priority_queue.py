from lapq import PriorityQueue


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
