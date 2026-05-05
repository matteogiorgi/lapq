#include <stdlib.h>

#include "lapq_internal.h"

static int lapq_reserve_slots(struct lapq *queue, size_t capacity)
{
    struct lapq_handle_slot *slots;
    size_t i;

    if (capacity <= queue->slot_capacity)
        return 0;
    slots = realloc(queue->slots, capacity * sizeof(*slots));
    if (slots == NULL)
        return -1;
    queue->slots = slots;
    for (i = queue->slot_capacity; i < capacity; i++) {
        queue->slots[i].owner = NULL;
        queue->slots[i].generation = 1;
        queue->slots[i].live = 0;
        queue->slots[i].next_free = (size_t)-1;
    }
    queue->slot_capacity = capacity;
    return 0;
}

int lapq_attach_handle(
    struct lapq *queue,
    struct lapq_node *node,
    struct lapq_handle *out
)
{
    struct lapq_handle_slot *slot;
    size_t index;
    size_t new_capacity;

    if (queue->free_slot != (size_t)-1) {
        index = queue->free_slot;
        slot = &queue->slots[index];
        queue->free_slot = slot->next_free;
    } else {
        if (queue->slot_count == queue->slot_capacity) {
            new_capacity = queue->slot_capacity == 0 ? 8 : queue->slot_capacity * 2;
            if (new_capacity < queue->slot_capacity)
                return -1;
            if (lapq_reserve_slots(queue, new_capacity) != 0)
                return -1;
        }
        index = queue->slot_count++;
    }

    slot = &queue->slots[index];
    slot->owner = node;
    slot->live = 1;
    slot->next_free = (size_t)-1;
    out->queue_id = queue->id;
    out->slot = index;
    out->generation = slot->generation;
    node->handle = *out;
    node->has_handle = 1;
    return 0;
}

int lapq_resolve_handle(
    const struct lapq *queue,
    struct lapq_handle handle,
    struct lapq_node **node
)
{
    const struct lapq_handle_slot *slot;

    if (queue == NULL || handle.queue_id != queue->id)
        return -1;
    if (handle.slot >= queue->slot_count)
        return -1;
    slot = &queue->slots[handle.slot];
    if (!slot->live || slot->generation != handle.generation)
        return -1;
    if (node != NULL)
        *node = slot->owner;
    return 0;
}

void lapq_release_handle(struct lapq *queue, struct lapq_handle handle)
{
    struct lapq_handle_slot *slot;

    if (handle.slot >= queue->slot_count)
        return;
    slot = &queue->slots[handle.slot];
    if (!slot->live || slot->generation != handle.generation)
        return;
    slot->owner = NULL;
    slot->live = 0;
    slot->generation++;
    if (slot->generation == 0)
        slot->generation = 1;
    slot->next_free = queue->free_slot;
    queue->free_slot = handle.slot;
}
