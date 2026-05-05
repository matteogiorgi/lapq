#ifndef LAPQ_LAPQ_H
#define LAPQ_LAPQ_H

#include <stddef.h>
#include <stdint.h>

typedef int (*lapq_cmp_fn)(const void *lhs, const void *rhs);

struct lapq;

enum lapq_flags {
    LAPQ_ENABLE_STATS = 1u << 0
};

struct lapq_config {
    uint64_t seed;
    unsigned flags;
};

/*
 * Instrumentation counters are meant for experiments, not for API-level
 * complexity guarantees. They count operations performed by this
 * implementation under LAPQ_ENABLE_STATS.
 */
struct lapq_stats {
    uint64_t clean_comparisons;
    uint64_t level0_steps;
    uint64_t express_steps;
    uint64_t backward_steps;
    uint64_t bottom_up_steps;
    uint64_t top_down_steps;
    uint64_t predecessor_hints;
    uint64_t rank_hints;
    uint64_t invalid_hints;
};

struct lapq_handle {
    uint64_t queue_id;
    size_t slot;
    unsigned generation;
};

enum lapq_hint_kind {
    LAPQ_HINT_NONE = 0,
    LAPQ_HINT_PREDECESSOR = 1,
    LAPQ_HINT_RANK = 2
};

struct lapq_hint {
    enum lapq_hint_kind kind;
    union {
        struct lapq_handle predecessor;
        size_t rank;
    } as;
};

struct lapq *lapq_create(lapq_cmp_fn cmp);
struct lapq *lapq_create_with_config(
    lapq_cmp_fn cmp,
    const struct lapq_config *config
);
void lapq_destroy(struct lapq *queue);

int lapq_insert(struct lapq *queue, void *item);
int lapq_insert_hint(struct lapq *queue, void *item, struct lapq_hint hint);
int lapq_insert_handle(struct lapq *queue, void *item, struct lapq_handle *out);
int lapq_insert_handle_hint(
    struct lapq *queue,
    void *item,
    struct lapq_hint hint,
    struct lapq_handle *out
);

/*
 * The caller owns items and their keys. For decrease_key, update the item's
 * key first, then call this function to reposition the existing node.
 */
int lapq_decrease_key(struct lapq *queue, struct lapq_handle handle);
int lapq_decrease_key_hint(
    struct lapq *queue,
    struct lapq_handle handle,
    struct lapq_hint hint
);
void *lapq_remove(struct lapq *queue, struct lapq_handle handle);

void *lapq_peek_min(const struct lapq *queue);
void *lapq_extract_min(struct lapq *queue);
size_t lapq_size(const struct lapq *queue);
int lapq_empty(const struct lapq *queue);
int lapq_check_invariants(const struct lapq *queue);

void lapq_get_stats(const struct lapq *queue, struct lapq_stats *out);
void lapq_reset_stats(struct lapq *queue);

#endif
