#ifndef LAPQ_INTERNAL_H
#define LAPQ_INTERNAL_H

/**
 * @file lapq_internal.h
 * @brief Private data structures shared by the LAPQ C modules.
 *
 * This header is intentionally not installed as public API. It describes the
 * concrete skip-list backend, the generational handle table, and the internal
 * instrumentation hooks used by the benchmark and tests.
 */

#include "lapq/lapq.h"

/** @brief Maximum number of skip-list levels allocated in every node. */
#define LAPQ_MAX_LEVEL 32

/** @brief One skip-list node storing a caller-owned item pointer. */
struct lapq_node {
    /** Forward links. Entries above `level` are kept NULL. */
    struct lapq_node *next[LAPQ_MAX_LEVEL];
    /** Backward links used for removal and hinted backward correction. */
    struct lapq_node *prev[LAPQ_MAX_LEVEL];
    /** Stable handle payload when `has_handle` is nonzero. */
    struct lapq_handle handle;
    /** Caller-owned item pointer. */
    void *item;
    /** Number of active levels in this node. */
    unsigned level;
    /** Whether this node owns a live handle-table slot. */
    int has_handle;
};

/** @brief Entry in the generational handle table. */
struct lapq_handle_slot {
    /** Owning `struct lapq_node *` while live. */
    void *owner;
    /** Generation used to invalidate stale handles after release. */
    unsigned generation;
    /** Whether this slot currently resolves to a node. */
    int live;
    /** Singly-linked free-list pointer when not live. */
    size_t next_free;
};

/** @brief Concrete queue implementation hidden behind public `struct lapq`. */
struct lapq {
    /** Clean comparator supplied by the caller. */
    lapq_cmp_fn cmp;
    /** Unique queue id used to reject cross-queue handles. */
    uint64_t id;
    /** xorshift RNG state used for skip-list heights. */
    uint64_t rng;
    /** Public configuration flags. */
    unsigned flags;
    /** Instrumentation counters. */
    struct lapq_stats stats;
    /** Sentinel node with `LAPQ_MAX_LEVEL` levels. */
    struct lapq_node head;
    /** Current highest nonempty skip-list level count. */
    unsigned level;
    /** Number of live nodes. */
    size_t size;
    /** Generational handle table. */
    struct lapq_handle_slot *slots;
    /** Number of allocated logical slots. */
    size_t slot_count;
    /** Physical slot array capacity. */
    size_t slot_capacity;
    /** Head of the free slot list, or `(size_t)-1`. */
    size_t free_slot;
};

/** @brief Search phase used to attribute traversal counters. */
enum lapq_search_phase {
    /** Moving left from a predecessor hint that overshot the target key. */
    LAPQ_SEARCH_BACKWARD,
    /** Moving right from a predicted predecessor using local top levels. */
    LAPQ_SEARCH_BOTTOM_UP,
    /** Ordinary top-down skip-list refinement. */
    LAPQ_SEARCH_TOP_DOWN
};

/** @brief Compare two items and count a clean comparison when stats are enabled. */
int lapq_compare(struct lapq *queue, const void *lhs, const void *rhs);

/** @brief Count one skip-list search step in the given phase. */
void lapq_count_search_step(
    struct lapq *queue,
    unsigned level,
    enum lapq_search_phase phase
);

/** @brief Draw a random skip-list level from the queue RNG. */
unsigned lapq_random_level(struct lapq *queue);

/** @brief Initialize the empty skip-list state inside `queue`. */
void lapq_skiplist_init(struct lapq *queue);

/** @brief Allocate and initialize a node of the given level. */
struct lapq_node *lapq_node_create(void *item, unsigned level);

/** @brief Free all skip-list nodes without freeing caller-owned items. */
void lapq_skiplist_destroy_nodes(struct lapq *queue);

/** @brief Insert a preallocated node using an optional prediction hint. */
void lapq_insert_node(
    struct lapq *queue,
    struct lapq_node *node,
    struct lapq_hint hint
);

/** @brief Unlink a node from every level without freeing or releasing handles. */
void lapq_unlink_node(struct lapq *queue, struct lapq_node *node);

/** @brief Validate internal skip-list and handle invariants. */
int lapq_skiplist_check_invariants(const struct lapq *queue);

/** @brief Attach a new generational handle-table slot to `node`. */
int lapq_attach_handle(
    struct lapq *queue,
    struct lapq_node *node,
    struct lapq_handle *out
);

/** @brief Resolve a live handle to its owning node. */
int lapq_resolve_handle(
    const struct lapq *queue,
    struct lapq_handle handle,
    struct lapq_node **node
);

/** @brief Release a live handle and recycle its slot. */
void lapq_release_handle(struct lapq *queue, struct lapq_handle handle);

#endif
