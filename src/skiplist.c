#include <stdlib.h>

#include "lapq_internal.h"

static uint64_t lapq_next_random(struct lapq *queue)
{
    uint64_t x = queue->rng;

    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    queue->rng = x == 0 ? UINT64_C(0x9e3779b97f4a7c15) : x;
    return queue->rng * UINT64_C(2685821657736338717);
}

unsigned lapq_random_level(struct lapq *queue)
{
    unsigned level = 1;
    uint64_t bits = lapq_next_random(queue);

    while (level < LAPQ_MAX_LEVEL && (bits & 1u) != 0u) {
        level++;
        bits >>= 1;
        if (bits == 0)
            bits = lapq_next_random(queue);
    }
    return level;
}

void lapq_skiplist_init(struct lapq *queue)
{
    unsigned i;

    queue->level = 1;
    queue->size = 0;
    queue->head.item = NULL;
    queue->head.level = LAPQ_MAX_LEVEL;
    queue->head.has_handle = 0;
    for (i = 0; i < LAPQ_MAX_LEVEL; i++) {
        queue->head.next[i] = NULL;
        queue->head.prev[i] = NULL;
    }
}

struct lapq_node *lapq_node_create(void *item, unsigned level)
{
    struct lapq_node *node = malloc(sizeof(*node));
    unsigned i;

    if (node == NULL)
        return NULL;
    for (i = 0; i < LAPQ_MAX_LEVEL; i++) {
        node->next[i] = NULL;
        node->prev[i] = NULL;
    }
    node->item = item;
    node->level = level;
    node->has_handle = 0;
    return node;
}

void lapq_skiplist_destroy_nodes(struct lapq *queue)
{
    struct lapq_node *node = queue->head.next[0];

    while (node != NULL) {
        struct lapq_node *next = node->next[0];

        free(node);
        node = next;
    }
}

static struct lapq_node *lapq_node_at_rank(struct lapq *queue, size_t rank)
{
    struct lapq_node *current = &queue->head;
    size_t i;

    if (rank > queue->size)
        rank = queue->size;
    for (i = 0; i < rank && current->next[0] != NULL; i++)
        current = current->next[0];
    return current;
}

static void lapq_find_predecessor_from_head(
    struct lapq *queue,
    void *item,
    struct lapq_node **update,
    unsigned levels_needed
)
{
    struct lapq_node *current = &queue->head;
    int level;

    for (level = (int)queue->level - 1; level >= 0; level--) {
        while (
            current->next[level] != NULL &&
            lapq_compare(queue, current->next[level]->item, item) < 0
            )
        {
            lapq_count_search_step(queue, (unsigned)level, LAPQ_SEARCH_TOP_DOWN);
            current = current->next[level];
        }
        if ((unsigned)level < levels_needed)
            update[level] = current;
    }
}

/*
 * A predecessor hint is allowed to be inaccurate. If it points to an item whose
 * key is not smaller than the inserted key, first move left using the highest
 * level available at each visited node. This handles the symmetric case omitted
 * by the paper's Algorithm 2, which assumes Pred(u, Q) <= u.
 */
static struct lapq_node *lapq_correct_backward(
    struct lapq *queue,
    struct lapq_node *start,
    void *item
)
{
    struct lapq_node *current = start;

    while (current != &queue->head && lapq_compare(queue, current->item, item) >= 0) {
        unsigned level = current->level - 1;

        lapq_count_search_step(queue, level, LAPQ_SEARCH_BACKWARD);
        current = current->prev[level];
    }
    return current;
}

/*
 * Bottom-up phase of the pointer-prediction search: starting from a key known
 * to be smaller than item, move through each visited node's top level until the
 * top-level successor would overshoot. This expands the search interval around
 * the predicted predecessor before the ordinary top-down refinement.
 */
static struct lapq_node *lapq_bottom_up_expand(
    struct lapq *queue,
    struct lapq_node *start,
    void *item
)
{
    struct lapq_node *current = start;

    while (current != &queue->head) {
        unsigned top = current->level - 1;

        if (
            current->next[top] == NULL ||
            lapq_compare(queue, current->next[top]->item, item) >= 0
            )
            break;
        lapq_count_search_step(queue, top, LAPQ_SEARCH_BOTTOM_UP);
        current = current->next[top];
    }
    return current;
}

/* Top-down skip-list search restricted to the interval found by the expansion. */
static struct lapq_node *lapq_top_down_refine(
    struct lapq *queue,
    struct lapq_node *start,
    void *item
)
{
    struct lapq_node *current = start;
    int level;

    for (level = (int)current->level - 1; level >= 0; level--) {
        while (
            current->next[level] != NULL &&
            lapq_compare(queue, current->next[level]->item, item) < 0
            )
        {
            lapq_count_search_step(queue, (unsigned)level, LAPQ_SEARCH_TOP_DOWN);
            current = current->next[level];
        }
    }
    return current;
}

/*
 * Find the true predecessor from a possibly inaccurate predecessor hint.
 * Invalid or detached hints are handled by the caller by falling back to the
 * head search. Valid hints use:
 *   1. backward correction if the hint is too far right,
 *   2. bottom-up expansion if the hint is a predecessor but too far left,
 *   3. top-down refinement to locate the exact predecessor.
 */
static struct lapq_node *lapq_find_predecessor_from_hint(
    struct lapq *queue,
    struct lapq_node *hint,
    void *item
)
{
    struct lapq_node *current = hint == NULL ? &queue->head : hint;

    if (current == &queue->head)
        return lapq_top_down_refine(queue, current, item);

    current = lapq_correct_backward(queue, current, item);
    if (current == &queue->head)
        return lapq_top_down_refine(queue, current, item);

    current = lapq_bottom_up_expand(queue, current, item);
    return lapq_top_down_refine(queue, current, item);
}

static void lapq_fill_update_from_predecessor(
    struct lapq *queue,
    struct lapq_node *predecessor,
    void *item,
    struct lapq_node **update,
    unsigned levels_needed
)
{
    struct lapq_node *current;
    int level;

    for (level = (int)levels_needed - 1; level >= 0; level--) {
        current = predecessor;
        while (current != &queue->head && current->level <= (unsigned)level)
            current = current->prev[0];
        while (
            current->next[level] != NULL &&
            lapq_compare(queue, current->next[level]->item, item) < 0
            )
        {
            lapq_count_search_step(queue, (unsigned)level, LAPQ_SEARCH_TOP_DOWN);
            current = current->next[level];
        }
        update[level] = current;
    }
}

static void lapq_find_update_from(
    struct lapq *queue,
    struct lapq_node *start,
    void *item,
    struct lapq_node **update,
    unsigned levels_needed
)
{
    struct lapq_node *predecessor;

    if (
        start == NULL ||
        start == &queue->head ||
        start->prev[0] == NULL
        )
    {
        lapq_find_predecessor_from_head(queue, item, update, levels_needed);
        return;
    }

    predecessor = lapq_find_predecessor_from_hint(queue, start, item);
    lapq_fill_update_from_predecessor(queue, predecessor, item, update, levels_needed);
}

static void lapq_find_update(
    struct lapq *queue,
    void *item,
    struct lapq_hint hint,
    struct lapq_node **update,
    unsigned levels_needed
)
{
    struct lapq_node *start = &queue->head;

    if (hint.kind == LAPQ_HINT_PREDECESSOR) {
        if ((queue->flags & LAPQ_ENABLE_STATS) != 0)
            queue->stats.predecessor_hints++;
        if (lapq_resolve_handle(queue, hint.as.predecessor, &start) != 0) {
            if ((queue->flags & LAPQ_ENABLE_STATS) != 0)
                queue->stats.invalid_hints++;
        }
    } else if (hint.kind == LAPQ_HINT_RANK) {
        if ((queue->flags & LAPQ_ENABLE_STATS) != 0)
            queue->stats.rank_hints++;
        start = lapq_node_at_rank(queue, hint.as.rank);
    }
    lapq_find_update_from(queue, start, item, update, levels_needed);
}

static void lapq_link_node(
    struct lapq *queue,
    struct lapq_node *node,
    struct lapq_node **update
)
{
    unsigned i;

    if (node->level > queue->level) {
        for (i = queue->level; i < node->level; i++)
            update[i] = &queue->head;
        queue->level = node->level;
    }
    for (i = 0; i < node->level; i++) {
        node->next[i] = update[i]->next[i];
        node->prev[i] = update[i];
        if (update[i]->next[i] != NULL)
            update[i]->next[i]->prev[i] = node;
        update[i]->next[i] = node;
    }
    queue->size++;
}

void lapq_unlink_node(struct lapq *queue, struct lapq_node *node)
{
    unsigned i;

    for (i = 0; i < node->level; i++) {
        if (node->prev[i] != NULL)
            node->prev[i]->next[i] = node->next[i];
        if (node->next[i] != NULL)
            node->next[i]->prev[i] = node->prev[i];
        node->next[i] = NULL;
        node->prev[i] = NULL;
    }
    while (queue->level > 1 && queue->head.next[queue->level - 1] == NULL)
        queue->level--;
    queue->size--;
}

void lapq_insert_node(
    struct lapq *queue,
    struct lapq_node *node,
    struct lapq_hint hint
)
{
    struct lapq_node *update[LAPQ_MAX_LEVEL];
    unsigned levels_needed = node->level < queue->level ? node->level : queue->level;

    lapq_find_update(queue, node->item, hint, update, levels_needed);
    lapq_link_node(queue, node, update);
}

int lapq_skiplist_check_invariants(const struct lapq *queue)
{
    const struct lapq_node *node;
    const struct lapq_node *previous;
    size_t count = 0;
    unsigned level;

    if (queue == NULL || queue->cmp == NULL || queue->id == 0)
        return -1;
    if (queue->level == 0 || queue->level > LAPQ_MAX_LEVEL)
        return -1;
    for (level = 0; level < queue->level; level++) {
        previous = &queue->head;
        node = queue->head.next[level];
        while (node != NULL) {
            if (node->level <= level)
                return -1;
            if (node->prev[level] != previous)
                return -1;
            if (previous != &queue->head && queue->cmp(previous->item, node->item) > 0)
                return -1;
            previous = node;
            node = node->next[level];
        }
    }
    previous = NULL;
    node = queue->head.next[0];
    while (node != NULL) {
        struct lapq_node *owner;

        if (previous != NULL && queue->cmp(previous->item, node->item) > 0)
            return -1;
        if (node->has_handle) {
            if (lapq_resolve_handle(queue, node->handle, &owner) != 0)
                return -1;
            if (owner != node)
                return -1;
        }
        count++;
        if (count > queue->size)
            return -1;
        previous = node;
        node = node->next[0];
    }
    return count == queue->size ? 0 : -1;
}
