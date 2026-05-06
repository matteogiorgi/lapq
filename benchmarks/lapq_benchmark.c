#define _POSIX_C_SOURCE 200809L

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "lapq/lapq.h"

/**
 * @file lapq_benchmark.c
 * @brief Standalone C benchmark for LAPQ hint scenarios.
 *
 * The benchmark is intentionally small and reproducible. It compares ordinary
 * insertions against perfect, noisy, and adversarial predecessor hints, then
 * runs a separate `decrease_key` workload. It reports both wall-clock time and
 * LAPQ's internal instrumentation counters so algorithmic behavior can be
 * inspected independently from timing noise.
 */

/** @brief Insertion workload variant. */
enum bench_mode {
    /** No hints. */
    BENCH_BASELINE,
    /** Each insertion receives the exact predecessor. */
    BENCH_PERFECT_HINT,
    /** Each insertion receives a predecessor with controlled left error. */
    BENCH_NOISY_HINT,
    /** Each insertion receives a very distant predecessor from the left. */
    BENCH_BAD_LEFT_HINT,
    /** Keys are descending while hints point near the previous insertion. */
    BENCH_BAD_RIGHT_HINT
};

/** @brief Item type used by the benchmark comparator. */
struct bench_item {
    uint64_t key;
    uint64_t id;
    struct lapq_handle handle;
};

/** @brief Aggregate prediction error for a scenario. */
struct error_stats {
    uint64_t total;
    uint64_t max;
    uint64_t count;
};

/** @brief Command-line benchmark options. */
struct bench_options {
    int csv;
    size_t count;
    size_t noise;
};

static int bench_cmp(const void *lhs, const void *rhs)
{
    const struct bench_item *left = lhs;
    const struct bench_item *right = rhs;

    if (left->key != right->key)
        return left->key < right->key ? -1 : 1;
    if (left->id != right->id)
        return left->id < right->id ? -1 : 1;
    return 0;
}

static double elapsed_seconds(struct timespec start, struct timespec end)
{
    return (double)(end.tv_sec - start.tv_sec) +
        (double)(end.tv_nsec - start.tv_nsec) / 1000000000.0;
}

static uint64_t consume_queue(struct lapq *queue)
{
    uint64_t checksum = 0;

    while (!lapq_empty(queue)) {
        const struct bench_item *item = lapq_extract_min(queue);

        checksum ^= item->key + UINT64_C(0x9e3779b97f4a7c15) + (item->id << 6);
    }
    return checksum;
}

static int insert_item(
    struct lapq *queue,
    struct bench_item *items,
    size_t index,
    enum bench_mode mode,
    size_t noise,
    struct error_stats *errors
)
{
    struct lapq_hint hint;
    size_t predecessor;
    size_t error = 0;

    hint.kind = LAPQ_HINT_NONE;
    if (mode == BENCH_BASELINE || index == 0)
        return lapq_insert_handle(queue, &items[index], &items[index].handle);

    hint.kind = LAPQ_HINT_PREDECESSOR;
    if (mode == BENCH_PERFECT_HINT) {
        predecessor = index - 1;
    } else if (mode == BENCH_NOISY_HINT) {
        predecessor = index > noise + 1 ? index - noise - 1 : 0;
    } else if (mode == BENCH_BAD_LEFT_HINT) {
        predecessor = 0;
    } else {
        predecessor = index - 1;
    }
    if (mode == BENCH_NOISY_HINT)
        error = index - predecessor - 1;
    else if (mode == BENCH_BAD_LEFT_HINT)
        error = index - 1;
    else if (mode == BENCH_BAD_RIGHT_HINT)
        error = 1;
    errors->total += error;
    if (error > errors->max)
        errors->max = error;
    errors->count++;
    hint.as.predecessor = items[predecessor].handle;
    return lapq_insert_handle_hint(queue, &items[index], hint, &items[index].handle);
}

static int run_scenario(
    const char *name,
    enum bench_mode mode,
    size_t count,
    size_t noise,
    int csv
)
{
    struct lapq_config config = { 123, LAPQ_ENABLE_STATS };
    struct bench_item *items = calloc(count, sizeof(*items));
    struct lapq *queue = lapq_create_with_config(bench_cmp, &config);
    struct lapq_stats stats;
    struct error_stats errors = { 0, 0, 0 };
    struct timespec start, end;
    uint64_t checksum;
    size_t i;

    if (items == NULL || queue == NULL) {
        free(items);
        lapq_destroy(queue);
        return 1;
    }

    clock_gettime(CLOCK_MONOTONIC, &start);
    for (i = 0; i < count; i++) {
        items[i].key = mode == BENCH_BAD_RIGHT_HINT ? count - i : i;
        items[i].id = i;
        if (insert_item(queue, items, i, mode, noise, &errors) != 0) {
            free(items);
            lapq_destroy(queue);
            return 1;
        }
    }
    checksum = consume_queue(queue);
    clock_gettime(CLOCK_MONOTONIC, &end);

    lapq_get_stats(queue, &stats);
    if (csv) {
        printf(
            "%s,%zu,%zu,%.9f,%" PRIu64 ",%" PRIu64 ",%" PRIu64
            ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
            ",%.3f,%" PRIu64 ",%" PRIu64 "\n",
            name,
            count,
            noise,
            elapsed_seconds(start, end),
            stats.clean_comparisons,
            stats.level0_steps,
            stats.express_steps,
            stats.backward_steps,
            stats.bottom_up_steps,
            stats.top_down_steps,
            stats.predecessor_hints,
            stats.invalid_hints,
            errors.count == 0 ? 0.0 : (double)errors.total / (double)errors.count,
            errors.max,
            checksum
        );
    } else {
        printf(
            "%-14s n=%zu seconds=%.9f clean_cmp=%" PRIu64
            " level0_steps=%" PRIu64 " express_steps=%" PRIu64
            " backward=%" PRIu64 " bottom_up=%" PRIu64 " top_down=%" PRIu64
            " pred_hints=%" PRIu64 " invalid_hints=%" PRIu64
            " avg_error=%.3f max_error=%" PRIu64
            " checksum=%" PRIu64 "\n",
            name,
            count,
            elapsed_seconds(start, end),
            stats.clean_comparisons,
            stats.level0_steps,
            stats.express_steps,
            stats.backward_steps,
            stats.bottom_up_steps,
            stats.top_down_steps,
            stats.predecessor_hints,
            stats.invalid_hints,
            errors.count == 0 ? 0.0 : (double)errors.total / (double)errors.count,
            errors.max,
            checksum
        );
    }
    lapq_destroy(queue);
    free(items);
    return 0;
}

static int run_decrease_scenario(size_t count, size_t noise, int csv)
{
    struct lapq_config config = { 123, LAPQ_ENABLE_STATS };
    struct bench_item *items = calloc(count, sizeof(*items));
    struct lapq *queue = lapq_create_with_config(bench_cmp, &config);
    struct lapq_stats stats;
    struct error_stats errors = { 0, 0, 0 };
    struct timespec start, end;
    uint64_t checksum;
    size_t i;

    if (items == NULL || queue == NULL) {
        free(items);
        lapq_destroy(queue);
        return 1;
    }

    for (i = 0; i < count; i++) {
        items[i].key = count + i;
        items[i].id = i;
        if (lapq_insert_handle(queue, &items[i], &items[i].handle) != 0) {
            free(items);
            lapq_destroy(queue);
            return 1;
        }
    }

    lapq_reset_stats(queue);
    clock_gettime(CLOCK_MONOTONIC, &start);
    for (i = count; i > 0; i--) {
        size_t index = i - 1;
        struct lapq_hint hint;

        items[index].key = index;
        hint.kind = LAPQ_HINT_NONE;
        if (index + noise + 1 < count) {
            size_t predecessor = index + noise + 1;
            uint64_t error = (uint64_t)(predecessor - index);

            hint.kind = LAPQ_HINT_PREDECESSOR;
            hint.as.predecessor = items[predecessor].handle;
            errors.total += error;
            if (error > errors.max)
                errors.max = error;
            errors.count++;
        }
        if (lapq_decrease_key_hint(queue, items[index].handle, hint) != 0) {
            free(items);
            lapq_destroy(queue);
            return 1;
        }
    }
    checksum = consume_queue(queue);
    clock_gettime(CLOCK_MONOTONIC, &end);

    lapq_get_stats(queue, &stats);
    if (csv) {
        printf(
            "%s,%zu,%zu,%.9f,%" PRIu64 ",%" PRIu64 ",%" PRIu64
            ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
            ",%.3f,%" PRIu64 ",%" PRIu64 "\n",
            "decrease",
            count,
            noise,
            elapsed_seconds(start, end),
            stats.clean_comparisons,
            stats.level0_steps,
            stats.express_steps,
            stats.backward_steps,
            stats.bottom_up_steps,
            stats.top_down_steps,
            stats.predecessor_hints,
            stats.invalid_hints,
            errors.count == 0 ? 0.0 : (double)errors.total / (double)errors.count,
            errors.max,
            checksum
        );
    } else {
        printf(
            "%-14s n=%zu seconds=%.9f clean_cmp=%" PRIu64
            " level0_steps=%" PRIu64 " express_steps=%" PRIu64
            " backward=%" PRIu64 " bottom_up=%" PRIu64 " top_down=%" PRIu64
            " pred_hints=%" PRIu64 " invalid_hints=%" PRIu64
            " avg_error=%.3f max_error=%" PRIu64
            " checksum=%" PRIu64 "\n",
            "decrease",
            count,
            elapsed_seconds(start, end),
            stats.clean_comparisons,
            stats.level0_steps,
            stats.express_steps,
            stats.backward_steps,
            stats.bottom_up_steps,
            stats.top_down_steps,
            stats.predecessor_hints,
            stats.invalid_hints,
            errors.count == 0 ? 0.0 : (double)errors.total / (double)errors.count,
            errors.max,
            checksum
        );
    }
    lapq_destroy(queue);
    free(items);
    return 0;
}

static struct bench_options parse_options(int argc, char **argv)
{
    struct bench_options options = { 0, 100000, 64 };
    int positional = 0;
    int i;

    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--csv") == 0) {
            options.csv = 1;
        } else if (positional == 0) {
            options.count = (size_t)strtoull(argv[i], NULL, 10);
            positional++;
        } else if (positional == 1) {
            options.noise = (size_t)strtoull(argv[i], NULL, 10);
            positional++;
        }
    }
    return options;
}

int main(int argc, char **argv)
{
    struct bench_options options = parse_options(argc, argv);

    if (options.count == 0)
        return 0;
    if (options.csv) {
        printf(
            "scenario,n,noise,seconds,clean_cmp,level0_steps,express_steps,"
            "backward,bottom_up,top_down,pred_hints,invalid_hints,"
            "avg_error,max_error,checksum\n"
        );
    }
    if (run_scenario(
        "baseline",
        BENCH_BASELINE,
        options.count,
        options.noise,
        options.csv
    ) != 0)
        return 1;
    if (run_scenario(
        "perfect",
        BENCH_PERFECT_HINT,
        options.count,
        options.noise,
        options.csv
    ) != 0)
        return 1;
    if (run_scenario(
        "noisy",
        BENCH_NOISY_HINT,
        options.count,
        options.noise,
        options.csv
    ) != 0)
        return 1;
    if (run_scenario(
        "bad-left",
        BENCH_BAD_LEFT_HINT,
        options.count,
        options.noise,
        options.csv
    ) != 0)
        return 1;
    if (run_scenario(
        "bad-right",
        BENCH_BAD_RIGHT_HINT,
        options.count,
        options.noise,
        options.csv
    ) != 0)
        return 1;
    if (run_decrease_scenario(options.count, options.noise, options.csv) != 0)
        return 1;
    return 0;
}
