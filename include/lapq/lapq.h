#ifndef LAPQ_LAPQ_H
#define LAPQ_LAPQ_H

/**
 * @file lapq.h
 * @brief Public C API for the LAPQ skip-list priority queue.
 *
 * LAPQ is an experimental learning-augmented priority queue core. The C API is
 * deliberately independent of any machine-learning framework: callers may pass
 * optional prediction hints, but ordering and correctness are always determined
 * by the clean comparator supplied at queue construction time.
 *
 * Items are caller-owned `void *` pointers. The queue stores the pointers but
 * never copies, mutates, or frees the pointed-to objects.
 */

#include <stddef.h>
#include <stdint.h>

/**
 * @brief Clean comparator used for all correctness-critical ordering.
 *
 * The comparator must return a negative value when `lhs < rhs`, zero when the
 * two items compare equal, and a positive value when `lhs > rhs`. The queue may
 * call this function during insertion, hinted correction, invariant checking,
 * and tests. The comparator is the only source of ordering truth.
 */
typedef int (*lapq_cmp_fn)(const void *lhs, const void *rhs);

/** @brief Opaque priority queue object. */
struct lapq;

/** @brief Optional queue flags. */
enum lapq_flags {
    /** Enable experimental comparison and traversal counters. */
    LAPQ_ENABLE_STATS = 1u << 0
};

/** @brief Queue construction parameters. */
struct lapq_config {
    /** Random seed used for deterministic skip-list level generation. */
    uint64_t seed;
    /** Bitwise OR of `enum lapq_flags` values. */
    unsigned flags;
};

/**
 * @brief Instrumentation counters collected when `LAPQ_ENABLE_STATS` is set.
 *
 * Instrumentation counters are meant for experiments, not for API-level
 * complexity guarantees. They count operations performed by this
 * implementation under LAPQ_ENABLE_STATS.
 */
struct lapq_stats {
    /** Clean comparator invocations. */
    uint64_t clean_comparisons;
    /** Search steps taken at skip-list level 0. */
    uint64_t level0_steps;
    /** Search steps taken above level 0. */
    uint64_t express_steps;
    /** Steps used while correcting a predecessor hint that is too far right. */
    uint64_t backward_steps;
    /** Steps used while expanding right from a predecessor hint. */
    uint64_t bottom_up_steps;
    /** Steps used by ordinary top-down skip-list refinement. */
    uint64_t top_down_steps;
    /** Number of predecessor hints received. */
    uint64_t predecessor_hints;
    /** Number of rank hints received. */
    uint64_t rank_hints;
    /** Number of predecessor hints rejected as stale, foreign, or invalid. */
    uint64_t invalid_hints;
};

/**
 * @brief Stable generational handle for an item stored in a queue.
 *
 * Handles are produced by handle-returning insertion functions. They can later
 * be used for `decrease_key`, hinted insertions, and arbitrary removal. A handle
 * is tied to one queue and one generation of one slot; after removal or
 * extraction, the old handle becomes stale and is rejected.
 */
struct lapq_handle {
    /** Queue identifier used to reject cross-queue handles. */
    uint64_t queue_id;
    /** Internal handle-table slot. */
    size_t slot;
    /** Generation counter used to reject stale handles. */
    unsigned generation;
};

/** @brief Kinds of prediction hint accepted by insertion and decrease-key. */
enum lapq_hint_kind {
    /** No prediction. Search starts from the head as in an ordinary skip list. */
    LAPQ_HINT_NONE = 0,
    /** Hint names an expected predecessor by handle. */
    LAPQ_HINT_PREDECESSOR = 1,
    /** Hint gives an expected insertion rank. Experimental in v0.1. */
    LAPQ_HINT_RANK = 2
};

/**
 * @brief Optional prediction supplied by the caller.
 *
 * Hints are advice, not proof. The implementation validates handles and then
 * corrects the predicted position with clean comparisons. Invalid hints cannot
 * break correctness; at worst they add work and increment instrumentation.
 */
struct lapq_hint {
    /** Active member of the hint union. */
    enum lapq_hint_kind kind;
    /** Payload selected by `kind`. */
    union {
        /** Expected predecessor used when `kind == LAPQ_HINT_PREDECESSOR`. */
        struct lapq_handle predecessor;
        /** Expected rank used when `kind == LAPQ_HINT_RANK`. */
        size_t rank;
    } as;
};

/** @brief Create a queue with default configuration. */
struct lapq *lapq_create(lapq_cmp_fn cmp);

/** @brief Create a queue with explicit seed and flags. */
struct lapq *lapq_create_with_config(
    lapq_cmp_fn cmp,
    const struct lapq_config *config
);

/** @brief Destroy a queue and its internal nodes. Caller-owned items are not freed. */
void lapq_destroy(struct lapq *queue);

/** @brief Insert `item` without a prediction hint. */
int lapq_insert(struct lapq *queue, void *item);

/** @brief Insert `item` using an optional prediction hint. */
int lapq_insert_hint(struct lapq *queue, void *item, struct lapq_hint hint);

/** @brief Insert `item` and return a handle for future operations. */
int lapq_insert_handle(struct lapq *queue, void *item, struct lapq_handle *out);

/** @brief Insert `item` with both a prediction hint and a returned handle. */
int lapq_insert_handle_hint(
    struct lapq *queue,
    void *item,
    struct lapq_hint hint,
    struct lapq_handle *out
);

/**
 * @brief Reposition an existing item after its key has decreased.
 *
 * The caller owns items and their keys. Update the item's key first, then call
 * this function with the handle returned at insertion time. The function
 * removes and reinserts the existing node; it does not allocate a new item.
 */
int lapq_decrease_key(struct lapq *queue, struct lapq_handle handle);

/** @brief Reposition an existing item after key decrease using a hint. */
int lapq_decrease_key_hint(
    struct lapq *queue,
    struct lapq_handle handle,
    struct lapq_hint hint
);

/** @brief Remove an item by handle and return the caller-owned item pointer. */
void *lapq_remove(struct lapq *queue, struct lapq_handle handle);

/** @brief Return the minimum item without removing it, or NULL if empty. */
void *lapq_peek_min(const struct lapq *queue);

/** @brief Remove and return the minimum item, or NULL if empty. */
void *lapq_extract_min(struct lapq *queue);

/** @brief Return the number of items currently stored in the queue. */
size_t lapq_size(const struct lapq *queue);

/** @brief Return nonzero when the queue is empty. */
int lapq_empty(const struct lapq *queue);

/** @brief Validate internal ordering, links, size, and handle consistency. */
int lapq_check_invariants(const struct lapq *queue);

/** @brief Copy current instrumentation counters into `out`. */
void lapq_get_stats(const struct lapq *queue, struct lapq_stats *out);

/** @brief Reset all instrumentation counters to zero. */
void lapq_reset_stats(struct lapq *queue);

#endif
