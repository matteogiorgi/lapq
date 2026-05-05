#include <assert.h>
#include <stdio.h>

#include "lapq/lapq.h"

struct item {
    int id;
    int key;
    struct lapq_handle handle;
};

static int int_cmp(const void *lhs, const void *rhs)
{
    const int *left = lhs;
    const int *right = rhs;

    return (*left > *right) - (*left < *right);
}

static int item_cmp(const void *lhs, const void *rhs)
{
    const struct item *left = lhs;
    const struct item *right = rhs;

    if (left->key != right->key)
        return (left->key > right->key) - (left->key < right->key);
    return (left->id > right->id) - (left->id < right->id);
}

static void test_insert_extract_order(void)
{
    int values[] = { 7, 3, 9, 1, 5 };
    int expected[] = { 1, 3, 5, 7, 9 };
    struct lapq_config config = { 123, 0 };
    struct lapq *queue = lapq_create_with_config(int_cmp, &config);
    size_t i;

    assert(queue != NULL);
    for (i = 0; i < sizeof(values) / sizeof(values[0]); i++)
        assert(lapq_insert(queue, &values[i]) == 0);
    assert(lapq_check_invariants(queue) == 0);
    for (i = 0; i < sizeof(expected) / sizeof(expected[0]); i++) {
        int *value = lapq_extract_min(queue);

        assert(value != NULL);
        assert(*value == expected[i]);
        assert(lapq_check_invariants(queue) == 0);
    }
    assert(lapq_empty(queue));
    lapq_destroy(queue);
}

static void test_handles_and_decrease(void)
{
    struct item items[] = {
        { 0, 40, { 0, 0, 0 } },
        { 1, 10, { 0, 0, 0 } },
        { 2, 30, { 0, 0, 0 } },
        { 3, 20, { 0, 0, 0 } }
    };
    struct lapq_config config = { 456, 0 };
    struct lapq *queue = lapq_create_with_config(item_cmp, &config);
    struct item *item;
    size_t i;

    assert(queue != NULL);
    for (i = 0; i < sizeof(items) / sizeof(items[0]); i++)
        assert(lapq_insert_handle(queue, &items[i], &items[i].handle) == 0);
    items[0].key = 5;
    assert(lapq_decrease_key(queue, items[0].handle) == 0);
    assert(lapq_check_invariants(queue) == 0);
    assert(lapq_peek_min(queue) == &items[0]);
    item = lapq_remove(queue, items[2].handle);
    assert(item == &items[2]);
    assert(lapq_remove(queue, items[2].handle) == NULL);
    item = lapq_extract_min(queue);
    assert(item == &items[0]);
    item = lapq_extract_min(queue);
    assert(item == &items[1]);
    item = lapq_extract_min(queue);
    assert(item == &items[3]);
    assert(lapq_empty(queue));
    lapq_destroy(queue);
}

static void test_hints(void)
{
    struct item items[] = {
        { 0, 10, { 0, 0, 0 } },
        { 1, 20, { 0, 0, 0 } },
        { 2, 30, { 0, 0, 0 } },
        { 3, 25, { 0, 0, 0 } },
        { 4, 5, { 0, 0, 0 } }
    };
    struct lapq_hint hint;
    struct lapq_config config = { 789, LAPQ_ENABLE_STATS };
    struct lapq_stats stats;
    struct lapq *queue = lapq_create_with_config(item_cmp, &config);

    assert(queue != NULL);
    assert(lapq_insert_handle(queue, &items[0], &items[0].handle) == 0);
    assert(lapq_insert_handle(queue, &items[1], &items[1].handle) == 0);
    assert(lapq_insert_handle(queue, &items[2], &items[2].handle) == 0);
    hint.kind = LAPQ_HINT_PREDECESSOR;
    hint.as.predecessor = items[1].handle;
    assert(lapq_insert_handle_hint(queue, &items[3], hint, &items[3].handle) == 0);
    hint.kind = LAPQ_HINT_RANK;
    hint.as.rank = 0;
    assert(lapq_insert_handle_hint(queue, &items[4], hint, &items[4].handle) == 0);
    assert(lapq_check_invariants(queue) == 0);
    lapq_get_stats(queue, &stats);
    assert(stats.clean_comparisons > 0);
    assert(stats.predecessor_hints == 1);
    assert(stats.rank_hints == 1);
    assert(stats.invalid_hints == 0);
    assert(lapq_extract_min(queue) == &items[4]);
    assert(lapq_extract_min(queue) == &items[0]);
    assert(lapq_extract_min(queue) == &items[1]);
    assert(lapq_extract_min(queue) == &items[3]);
    assert(lapq_extract_min(queue) == &items[2]);
    lapq_destroy(queue);
}

static void test_duplicate_keys(void)
{
    struct item items[] = {
        { 0, 10, { 0, 0, 0 } },
        { 1, 10, { 0, 0, 0 } },
        { 2, 5, { 0, 0, 0 } },
        { 3, 10, { 0, 0, 0 } }
    };
    struct lapq_config config = { 321, 0 };
    struct lapq *queue = lapq_create_with_config(item_cmp, &config);
    size_t i;

    assert(queue != NULL);
    for (i = 0; i < sizeof(items) / sizeof(items[0]); i++)
        assert(lapq_insert_handle(queue, &items[i], &items[i].handle) == 0);
    assert(lapq_check_invariants(queue) == 0);
    assert(lapq_extract_min(queue) == &items[2]);
    assert(lapq_extract_min(queue) == &items[0]);
    assert(lapq_extract_min(queue) == &items[1]);
    assert(lapq_extract_min(queue) == &items[3]);
    assert(lapq_empty(queue));
    lapq_destroy(queue);
}

static void test_bad_and_stale_hints(void)
{
    struct item items[] = {
        { 0, 10, { 0, 0, 0 } },
        { 1, 20, { 0, 0, 0 } },
        { 2, 30, { 0, 0, 0 } },
        { 3, 15, { 0, 0, 0 } },
        { 4, 25, { 0, 0, 0 } },
        { 5, 5, { 0, 0, 0 } }
    };
    struct item foreign = { 99, 99, { 0, 0, 0 } };
    struct lapq_config config = { 654, LAPQ_ENABLE_STATS };
    struct lapq *queue = lapq_create_with_config(item_cmp, &config);
    struct lapq *other = lapq_create_with_config(item_cmp, &config);
    struct lapq_hint hint;
    struct lapq_stats stats;

    assert(queue != NULL);
    assert(other != NULL);
    assert(lapq_insert_handle(queue, &items[0], &items[0].handle) == 0);
    assert(lapq_insert_handle(queue, &items[1], &items[1].handle) == 0);
    assert(lapq_insert_handle(queue, &items[2], &items[2].handle) == 0);

    hint.kind = LAPQ_HINT_PREDECESSOR;
    hint.as.predecessor = items[2].handle;
    assert(lapq_insert_handle_hint(queue, &items[3], hint, &items[3].handle) == 0);
    assert(lapq_check_invariants(queue) == 0);

    assert(lapq_insert_handle(other, &foreign, &foreign.handle) == 0);
    hint.as.predecessor = foreign.handle;
    assert(lapq_insert_handle_hint(queue, &items[4], hint, &items[4].handle) == 0);
    assert(lapq_check_invariants(queue) == 0);

    assert(lapq_remove(other, foreign.handle) == &foreign);
    hint.as.predecessor = foreign.handle;
    assert(lapq_insert_handle_hint(queue, &items[5], hint, &items[5].handle) == 0);
    assert(lapq_check_invariants(queue) == 0);

    lapq_get_stats(queue, &stats);
    assert(stats.predecessor_hints == 3);
    assert(stats.invalid_hints == 2);
    assert(lapq_extract_min(queue) == &items[5]);
    assert(lapq_extract_min(queue) == &items[0]);
    assert(lapq_extract_min(queue) == &items[3]);
    assert(lapq_extract_min(queue) == &items[1]);
    assert(lapq_extract_min(queue) == &items[4]);
    assert(lapq_extract_min(queue) == &items[2]);
    assert(lapq_empty(queue));
    lapq_destroy(other);
    lapq_destroy(queue);
}

static void test_hint_search_phases(void)
{
    enum { ITEM_COUNT = 128 };
    struct item items[ITEM_COUNT + 4];
    struct lapq_config config = { 777, LAPQ_ENABLE_STATS };
    struct lapq *queue = lapq_create_with_config(item_cmp, &config);
    struct lapq_hint hint;
    struct lapq_stats stats;
    size_t i;

    assert(queue != NULL);
    for (i = 0; i < ITEM_COUNT; i++) {
        items[i].id = (int)i;
        items[i].key = (int)(i * 10);
        assert(lapq_insert_handle(queue, &items[i], &items[i].handle) == 0);
    }
    assert(lapq_check_invariants(queue) == 0);

    lapq_reset_stats(queue);
    items[ITEM_COUNT].id = ITEM_COUNT;
    items[ITEM_COUNT].key = 645;
    hint.kind = LAPQ_HINT_PREDECESSOR;
    hint.as.predecessor = items[64].handle;
    assert(lapq_insert_handle_hint(
        queue,
        &items[ITEM_COUNT],
        hint,
        &items[ITEM_COUNT].handle
    ) == 0);
    lapq_get_stats(queue, &stats);
    assert(stats.predecessor_hints == 1);
    assert(stats.backward_steps == 0);
    assert(stats.bottom_up_steps == 0);

    lapq_reset_stats(queue);
    items[ITEM_COUNT + 1].id = ITEM_COUNT + 1;
    items[ITEM_COUNT + 1].key = 1005;
    hint.as.predecessor = items[10].handle;
    assert(lapq_insert_handle_hint(
        queue,
        &items[ITEM_COUNT + 1],
        hint,
        &items[ITEM_COUNT + 1].handle
    ) == 0);
    lapq_get_stats(queue, &stats);
    assert(stats.predecessor_hints == 1);
    assert(stats.backward_steps == 0);
    assert(stats.bottom_up_steps > 0 || stats.top_down_steps > 0);

    lapq_reset_stats(queue);
    items[ITEM_COUNT + 2].id = ITEM_COUNT + 2;
    items[ITEM_COUNT + 2].key = 205;
    hint.as.predecessor = items[100].handle;
    assert(lapq_insert_handle_hint(
        queue,
        &items[ITEM_COUNT + 2],
        hint,
        &items[ITEM_COUNT + 2].handle
    ) == 0);
    lapq_get_stats(queue, &stats);
    assert(stats.predecessor_hints == 1);
    assert(stats.backward_steps > 0);

    lapq_reset_stats(queue);
    items[ITEM_COUNT + 3].id = ITEM_COUNT + 3;
    items[ITEM_COUNT + 3].key = -5;
    hint.as.predecessor = items[100].handle;
    assert(lapq_remove(queue, items[100].handle) == &items[100]);
    assert(lapq_insert_handle_hint(
        queue,
        &items[ITEM_COUNT + 3],
        hint,
        &items[ITEM_COUNT + 3].handle
    ) == 0);
    lapq_get_stats(queue, &stats);
    assert(stats.predecessor_hints == 1);
    assert(stats.invalid_hints == 1);
    assert(stats.backward_steps == 0);
    assert(stats.bottom_up_steps == 0);
    assert(lapq_check_invariants(queue) == 0);
    lapq_destroy(queue);
}

static unsigned next_random(unsigned *state)
{
    *state = *state * 1103515245u + 12345u;
    return *state;
}

static int find_min_active(
    const struct item *items,
    const int *active,
    size_t count,
    size_t *index
)
{
    size_t i;
    int found = 0;

    for (i = 0; i < count; i++) {
        if (!active[i])
            continue;
        if (!found || item_cmp(&items[i], &items[*index]) < 0) {
            *index = i;
            found = 1;
        }
    }
    return found ? 0 : -1;
}

static size_t count_active(const int *active, size_t count)
{
    size_t active_count = 0;
    size_t i;

    for (i = 0; i < count; i++) {
        if (active[i])
            active_count++;
    }
    return active_count;
}

static size_t select_nth(const int *active, size_t count, size_t ordinal, int want_active)
{
    size_t i;
    size_t seen = 0;

    for (i = 0; i < count; i++) {
        if (!!active[i] != !!want_active)
            continue;
        if (seen == ordinal)
            return i;
        seen++;
    }
    return count;
}

static void test_randomized_oracle(void)
{
    enum { ITEM_COUNT = 96, STEP_COUNT = 3000 };
    struct item items[ITEM_COUNT];
    int active[ITEM_COUNT];
    struct lapq_config config = { 999, LAPQ_ENABLE_STATS };
    struct lapq_stats stats;
    struct lapq *queue = lapq_create_with_config(item_cmp, &config);
    unsigned rng = 0x1234abcd;
    size_t i;
    size_t step;

    assert(queue != NULL);
    for (i = 0; i < ITEM_COUNT; i++) {
        items[i].id = (int)i;
        items[i].key = 0;
        active[i] = 0;
    }

    for (step = 0; step < STEP_COUNT; step++) {
        size_t active_count = count_active(active, ITEM_COUNT);
        unsigned choice = next_random(&rng) % 100u;
        size_t index;

        if (active_count == 0 || choice < 35u) {
            size_t inactive_count = ITEM_COUNT - active_count;
            struct lapq_hint hint;

            if (inactive_count == 0)
                continue;
            index = select_nth(
                active,
                ITEM_COUNT,
                next_random(&rng) % inactive_count,
                0
            );
            items[index].key = (int)(next_random(&rng) % 1000u) - 500;
            hint.kind = LAPQ_HINT_RANK;
            hint.as.rank = next_random(&rng) % (active_count + 1);
            assert(
                lapq_insert_handle_hint(
                    queue,
                    &items[index],
                    hint,
                    &items[index].handle
                ) == 0
            );
            active[index] = 1;
        } else if (choice < 65u) {
            struct lapq_hint hint;

            index = select_nth(
                active,
                ITEM_COUNT,
                next_random(&rng) % active_count,
                1
            );
            items[index].key -= 1 + (int)(next_random(&rng) % 50u);
            hint.kind = LAPQ_HINT_PREDECESSOR;
            hint.as.predecessor = items[index].handle;
            assert(lapq_decrease_key_hint(queue, items[index].handle, hint) == 0);
        } else if (choice < 82u) {
            struct item *removed;

            index = select_nth(
                active,
                ITEM_COUNT,
                next_random(&rng) % active_count,
                1
            );
            removed = lapq_remove(queue, items[index].handle);
            assert(removed == &items[index]);
            active[index] = 0;
        } else {
            size_t min_index;
            struct item *extracted;

            assert(find_min_active(items, active, ITEM_COUNT, &min_index) == 0);
            extracted = lapq_extract_min(queue);
            assert(extracted == &items[min_index]);
            active[extracted->id] = 0;
        }
        assert(lapq_size(queue) == count_active(active, ITEM_COUNT));
        assert(lapq_check_invariants(queue) == 0);
    }

    while (!lapq_empty(queue)) {
        size_t min_index;
        struct item *extracted;

        assert(find_min_active(items, active, ITEM_COUNT, &min_index) == 0);
        extracted = lapq_extract_min(queue);
        assert(extracted == &items[min_index]);
        active[extracted->id] = 0;
    }

    assert(count_active(active, ITEM_COUNT) == 0);
    lapq_get_stats(queue, &stats);
    assert(stats.clean_comparisons > 0);
    assert(stats.rank_hints > 0);
    assert(stats.predecessor_hints > 0);
    lapq_reset_stats(queue);
    lapq_get_stats(queue, &stats);
    assert(stats.clean_comparisons == 0);
    assert(stats.level0_steps == 0);
    assert(stats.express_steps == 0);
    assert(stats.backward_steps == 0);
    assert(stats.bottom_up_steps == 0);
    assert(stats.top_down_steps == 0);
    assert(stats.rank_hints == 0);
    assert(stats.predecessor_hints == 0);
    assert(stats.invalid_hints == 0);
    lapq_destroy(queue);
}

int main(void)
{
    assert(lapq_create(NULL) == NULL);
    test_insert_extract_order();
    test_handles_and_decrease();
    test_hints();
    test_duplicate_keys();
    test_bad_and_stale_hints();
    test_hint_search_phases();
    test_randomized_oracle();
    printf("All lapq tests passed\n");
    return 0;
}
