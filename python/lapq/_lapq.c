#define PY_SSIZE_T_CLEAN

#include <Python.h>
#include <stdint.h>
#include <stdlib.h>

#include "lapq/lapq.h"

struct py_lapq_item {
    double key;
    uint64_t sequence;
    PyObject *value;
};

typedef struct {
    PyObject_HEAD
    struct lapq *queue;
    uint64_t next_sequence;
} PyLapqPriorityQueue;

static int py_lapq_item_cmp(const void *lhs, const void *rhs)
{
    const struct py_lapq_item *left = lhs;
    const struct py_lapq_item *right = rhs;

    if (left->key < right->key)
        return -1;
    if (left->key > right->key)
        return 1;
    if (left->sequence < right->sequence)
        return -1;
    if (left->sequence > right->sequence)
        return 1;
    return 0;
}

static void py_lapq_item_destroy(struct py_lapq_item *item)
{
    if (item == NULL)
        return;
    Py_XDECREF(item->value);
    free(item);
}

static PyObject *PyLapqPriorityQueue_new(
    PyTypeObject *type,
    PyObject *args,
    PyObject *kwargs
)
{
    PyLapqPriorityQueue *self;
    struct lapq_config config = { 0, LAPQ_ENABLE_STATS };

    (void)args;
    (void)kwargs;
    self = (PyLapqPriorityQueue *)type->tp_alloc(type, 0);
    if (self == NULL)
        return NULL;
    self->queue = lapq_create_with_config(py_lapq_item_cmp, &config);
    if (self->queue == NULL) {
        Py_DECREF(self);
        PyErr_NoMemory();
        return NULL;
    }
    self->next_sequence = 0;
    return (PyObject *)self;
}

static void PyLapqPriorityQueue_dealloc(PyLapqPriorityQueue *self)
{
    if (self->queue != NULL) {
        while (!lapq_empty(self->queue)) {
            struct py_lapq_item *item = lapq_extract_min(self->queue);

            py_lapq_item_destroy(item);
        }
        lapq_destroy(self->queue);
        self->queue = NULL;
    }
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *PyLapqPriorityQueue_push(
    PyLapqPriorityQueue *self,
    PyObject *args
)
{
    double key;
    PyObject *value;
    struct py_lapq_item *item;

    if (!PyArg_ParseTuple(args, "dO:push", &key, &value))
        return NULL;
    item = malloc(sizeof(*item));
    if (item == NULL)
        return PyErr_NoMemory();
    item->key = key;
    item->sequence = self->next_sequence++;
    Py_INCREF(value);
    item->value = value;
    if (lapq_insert(self->queue, item) != 0) {
        py_lapq_item_destroy(item);
        return PyErr_NoMemory();
    }
    Py_RETURN_NONE;
}

static PyObject *PyLapqPriorityQueue_pop(PyLapqPriorityQueue *self, PyObject *Py_UNUSED(ignored))
{
    struct py_lapq_item *item;
    PyObject *result;

    item = lapq_extract_min(self->queue);
    if (item == NULL) {
        PyErr_SetString(PyExc_IndexError, "pop from empty PriorityQueue");
        return NULL;
    }
    result = Py_BuildValue("(dO)", item->key, item->value);
    py_lapq_item_destroy(item);
    return result;
}

static PyObject *PyLapqPriorityQueue_peek(PyLapqPriorityQueue *self, PyObject *Py_UNUSED(ignored))
{
    const struct py_lapq_item *item = lapq_peek_min(self->queue);

    if (item == NULL) {
        PyErr_SetString(PyExc_IndexError, "peek from empty PriorityQueue");
        return NULL;
    }
    return Py_BuildValue("(dO)", item->key, item->value);
}

static PyObject *PyLapqPriorityQueue_clear(
    PyLapqPriorityQueue *self,
    PyObject *Py_UNUSED(ignored)
)
{
    while (!lapq_empty(self->queue)) {
        struct py_lapq_item *item = lapq_extract_min(self->queue);

        py_lapq_item_destroy(item);
    }
    Py_RETURN_NONE;
}

static PyObject *PyLapqPriorityQueue_empty(
    PyLapqPriorityQueue *self,
    PyObject *Py_UNUSED(ignored)
)
{
    if (lapq_empty(self->queue))
        Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

static PyObject *PyLapqPriorityQueue_stats(
    PyLapqPriorityQueue *self,
    PyObject *Py_UNUSED(ignored)
)
{
    struct lapq_stats stats;

    lapq_get_stats(self->queue, &stats);
    return Py_BuildValue(
        "{s:K,s:K,s:K,s:K,s:K,s:K,s:K,s:K,s:K}",
        "clean_comparisons",
        (unsigned long long)stats.clean_comparisons,
        "level0_steps",
        (unsigned long long)stats.level0_steps,
        "express_steps",
        (unsigned long long)stats.express_steps,
        "backward_steps",
        (unsigned long long)stats.backward_steps,
        "bottom_up_steps",
        (unsigned long long)stats.bottom_up_steps,
        "top_down_steps",
        (unsigned long long)stats.top_down_steps,
        "predecessor_hints",
        (unsigned long long)stats.predecessor_hints,
        "rank_hints",
        (unsigned long long)stats.rank_hints,
        "invalid_hints",
        (unsigned long long)stats.invalid_hints
    );
}

static PyObject *PyLapqPriorityQueue_reset_stats(
    PyLapqPriorityQueue *self,
    PyObject *Py_UNUSED(ignored)
)
{
    lapq_reset_stats(self->queue);
    Py_RETURN_NONE;
}

static Py_ssize_t PyLapqPriorityQueue_len(PyLapqPriorityQueue *self)
{
    size_t size = lapq_size(self->queue);

    if (size > (size_t)PY_SSIZE_T_MAX) {
        PyErr_SetString(PyExc_OverflowError, "PriorityQueue size exceeds Py_ssize_t");
        return -1;
    }
    return (Py_ssize_t)size;
}

static PyMethodDef PyLapqPriorityQueue_methods[] = {
    { "push", (PyCFunction)PyLapqPriorityQueue_push, METH_VARARGS, "Push value with numeric priority." },
    { "pop", (PyCFunction)PyLapqPriorityQueue_pop, METH_NOARGS, "Remove and return the minimum (key, value)." },
    { "peek", (PyCFunction)PyLapqPriorityQueue_peek, METH_NOARGS, "Return the minimum (key, value) without removing it." },
    { "clear", (PyCFunction)PyLapqPriorityQueue_clear, METH_NOARGS, "Remove all items." },
    { "empty", (PyCFunction)PyLapqPriorityQueue_empty, METH_NOARGS, "Return True if the queue is empty." },
    { "stats", (PyCFunction)PyLapqPriorityQueue_stats, METH_NOARGS, "Return instrumentation counters." },
    { "reset_stats", (PyCFunction)PyLapqPriorityQueue_reset_stats, METH_NOARGS, "Reset instrumentation counters." },
    { NULL, NULL, 0, NULL }
};

static PySequenceMethods PyLapqPriorityQueue_sequence = {
    .sq_length = (lenfunc)PyLapqPriorityQueue_len,
};

static PyTypeObject PyLapqPriorityQueueType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "lapq.PriorityQueue",
    .tp_basicsize = sizeof(PyLapqPriorityQueue),
    .tp_dealloc = (destructor)PyLapqPriorityQueue_dealloc,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_doc = "Priority queue backed by the LAPQ C skip-list core.",
    .tp_methods = PyLapqPriorityQueue_methods,
    .tp_as_sequence = &PyLapqPriorityQueue_sequence,
    .tp_new = PyLapqPriorityQueue_new,
};

static PyMethodDef lapq_methods[] = {
    { NULL, NULL, 0, NULL }
};

static struct PyModuleDef lapq_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_lapq",
    .m_doc = "C extension for LAPQ.",
    .m_size = -1,
    .m_methods = lapq_methods,
};

PyMODINIT_FUNC PyInit__lapq(void)
{
    PyObject *module;

    if (PyType_Ready(&PyLapqPriorityQueueType) < 0)
        return NULL;
    module = PyModule_Create(&lapq_module);
    if (module == NULL)
        return NULL;
    Py_INCREF(&PyLapqPriorityQueueType);
    if (PyModule_AddObject(module, "PriorityQueue", (PyObject *)&PyLapqPriorityQueueType) < 0) {
        Py_DECREF(&PyLapqPriorityQueueType);
        Py_DECREF(module);
        return NULL;
    }
    return module;
}
