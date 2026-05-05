#include <stdlib.h>

#include "lapq_internal.h"

static uint64_t lapq_next_id = 1;

struct lapq *lapq_create(lapq_cmp_fn cmp)
{
    return lapq_create_with_config(cmp, NULL);
}

struct lapq *lapq_create_with_config(
    lapq_cmp_fn cmp,
    const struct lapq_config *config
)
{
    struct lapq *queue;
    uint64_t seed = UINT64_C(0x5eed1234cafef00d);

    if (cmp == NULL)
        return NULL;
    if (config != NULL && config->seed != 0)
        seed = config->seed;

    queue = malloc(sizeof(*queue));
    if (queue == NULL)
        return NULL;

    queue->cmp = cmp;
    queue->id = lapq_next_id++;
    if (queue->id == 0)
        queue->id = lapq_next_id++;
    queue->rng = seed;
    queue->flags = config == NULL ? 0 : config->flags;
    lapq_reset_stats(queue);
    lapq_skiplist_init(queue);
    queue->slots = NULL;
    queue->slot_count = 0;
    queue->slot_capacity = 0;
    queue->free_slot = (size_t)-1;
    return queue;
}

void lapq_destroy(struct lapq *queue)
{
    if (queue == NULL)
        return;
    lapq_skiplist_destroy_nodes(queue);
    free(queue->slots);
    free(queue);
}

int lapq_insert(struct lapq *queue, void *item)
{
    struct lapq_hint hint;

    hint.kind = LAPQ_HINT_NONE;
    return lapq_insert_hint(queue, item, hint);
}

int lapq_insert_hint(struct lapq *queue, void *item, struct lapq_hint hint)
{
    struct lapq_node *node;

    if (queue == NULL)
        return -1;
    node = lapq_node_create(item, lapq_random_level(queue));
    if (node == NULL)
        return -1;
    lapq_insert_node(queue, node, hint);
    return 0;
}

int lapq_insert_handle(
    struct lapq *queue,
    void *item,
    struct lapq_handle *out
)
{
    struct lapq_hint hint;

    hint.kind = LAPQ_HINT_NONE;
    return lapq_insert_handle_hint(queue, item, hint, out);
}

int lapq_insert_handle_hint(
    struct lapq *queue,
    void *item,
    struct lapq_hint hint,
    struct lapq_handle *out
)
{
    struct lapq_node *node;

    if (queue == NULL || out == NULL)
        return -1;
    node = lapq_node_create(item, lapq_random_level(queue));
    if (node == NULL)
        return -1;
    if (lapq_attach_handle(queue, node, out) != 0) {
        free(node);
        return -1;
    }
    lapq_insert_node(queue, node, hint);
    return 0;
}

int lapq_decrease_key(struct lapq *queue, struct lapq_handle handle)
{
    struct lapq_hint hint;

    hint.kind = LAPQ_HINT_NONE;
    return lapq_decrease_key_hint(queue, handle, hint);
}

int lapq_decrease_key_hint(
    struct lapq *queue,
    struct lapq_handle handle,
    struct lapq_hint hint
)
{
    struct lapq_node *node;

    if (lapq_resolve_handle(queue, handle, &node) != 0)
        return -1;
    lapq_unlink_node(queue, node);
    lapq_insert_node(queue, node, hint);
    return 0;
}

void *lapq_remove(struct lapq *queue, struct lapq_handle handle)
{
    struct lapq_node *node;
    void *item;

    if (lapq_resolve_handle(queue, handle, &node) != 0)
        return NULL;
    item = node->item;
    lapq_unlink_node(queue, node);
    lapq_release_handle(queue, handle);
    free(node);
    return item;
}

void *lapq_peek_min(const struct lapq *queue)
{
    if (queue == NULL || queue->head.next[0] == NULL)
        return NULL;
    return queue->head.next[0]->item;
}

void *lapq_extract_min(struct lapq *queue)
{
    struct lapq_node *node;
    void *item;

    if (queue == NULL || queue->head.next[0] == NULL)
        return NULL;
    node = queue->head.next[0];
    item = node->item;
    lapq_unlink_node(queue, node);
    if (node->has_handle)
        lapq_release_handle(queue, node->handle);
    free(node);
    return item;
}

size_t lapq_size(const struct lapq *queue)
{
    return queue == NULL ? 0 : queue->size;
}

int lapq_empty(const struct lapq *queue)
{
    return lapq_size(queue) == 0;
}

int lapq_check_invariants(const struct lapq *queue)
{
    return lapq_skiplist_check_invariants(queue);
}
