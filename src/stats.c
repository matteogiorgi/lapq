#include "lapq_internal.h"

/**
 * @file stats.c
 * @brief Instrumentation helpers for comparisons and skip-list traversal.
 *
 * Counters in this module are experimental observability tools. They are not
 * part of a formal complexity contract; instead, benchmarks use them to compare
 * baseline insertion, accurate predictions, noisy predictions, and adversarial
 * hints under the current implementation.
 */

int lapq_compare(struct lapq *queue, const void *lhs, const void *rhs)
{
    if ((queue->flags & LAPQ_ENABLE_STATS) != 0)
        queue->stats.clean_comparisons++;
    return queue->cmp(lhs, rhs);
}

static void lapq_count_step(struct lapq *queue, unsigned level)
{
    if ((queue->flags & LAPQ_ENABLE_STATS) == 0)
        return;
    if (level == 0)
        queue->stats.level0_steps++;
    else
        queue->stats.express_steps++;
}

void lapq_count_search_step(
    struct lapq *queue,
    unsigned level,
    enum lapq_search_phase phase
)
{
    if ((queue->flags & LAPQ_ENABLE_STATS) == 0)
        return;
    lapq_count_step(queue, level);
    if (phase == LAPQ_SEARCH_BACKWARD)
        queue->stats.backward_steps++;
    else if (phase == LAPQ_SEARCH_BOTTOM_UP)
        queue->stats.bottom_up_steps++;
    else
        queue->stats.top_down_steps++;
}

void lapq_get_stats(const struct lapq *queue, struct lapq_stats *out)
{
    if (out == NULL)
        return;
    if (queue == NULL) {
        struct lapq_stats empty = { 0, 0, 0, 0, 0, 0, 0, 0, 0 };

        *out = empty;
        return;
    }
    *out = queue->stats;
}

void lapq_reset_stats(struct lapq *queue)
{
    if (queue == NULL)
        return;
    queue->stats.clean_comparisons = 0;
    queue->stats.level0_steps = 0;
    queue->stats.express_steps = 0;
    queue->stats.backward_steps = 0;
    queue->stats.bottom_up_steps = 0;
    queue->stats.top_down_steps = 0;
    queue->stats.predecessor_hints = 0;
    queue->stats.rank_hints = 0;
    queue->stats.invalid_hints = 0;
}
