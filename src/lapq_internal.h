#ifndef LAPQ_INTERNAL_H
#define LAPQ_INTERNAL_H

#include "lapq/lapq.h"

#define LAPQ_MAX_LEVEL 32

struct lapq_node {
    struct lapq_node *next[LAPQ_MAX_LEVEL];
    struct lapq_node *prev[LAPQ_MAX_LEVEL];
    struct lapq_handle handle;
    void *item;
    unsigned level;
    int has_handle;
};

struct lapq_handle_slot {
    void *owner;
    unsigned generation;
    int live;
    size_t next_free;
};

struct lapq {
    lapq_cmp_fn cmp;
    uint64_t id;
    uint64_t rng;
    unsigned flags;
    struct lapq_stats stats;
    struct lapq_node head;
    unsigned level;
    size_t size;
    struct lapq_handle_slot *slots;
    size_t slot_count;
    size_t slot_capacity;
    size_t free_slot;
};

enum lapq_search_phase {
    LAPQ_SEARCH_BACKWARD,
    LAPQ_SEARCH_BOTTOM_UP,
    LAPQ_SEARCH_TOP_DOWN
};

int lapq_compare(struct lapq *queue, const void *lhs, const void *rhs);
void lapq_count_search_step(
    struct lapq *queue,
    unsigned level,
    enum lapq_search_phase phase
);

unsigned lapq_random_level(struct lapq *queue);
void lapq_skiplist_init(struct lapq *queue);
struct lapq_node *lapq_node_create(void *item, unsigned level);
void lapq_skiplist_destroy_nodes(struct lapq *queue);
void lapq_insert_node(
    struct lapq *queue,
    struct lapq_node *node,
    struct lapq_hint hint
);
void lapq_unlink_node(struct lapq *queue, struct lapq_node *node);
int lapq_skiplist_check_invariants(const struct lapq *queue);

int lapq_attach_handle(
    struct lapq *queue,
    struct lapq_node *node,
    struct lapq_handle *out
);
int lapq_resolve_handle(
    const struct lapq *queue,
    struct lapq_handle handle,
    struct lapq_node **node
);
void lapq_release_handle(struct lapq *queue, struct lapq_handle handle);

#endif
