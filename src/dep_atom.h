/* Copyright 2026 Gentoo Authors
 * SPDX-License-Identifier: GPL-2.0-or-later OR MIT
 */

#pragma once

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "dep_parser_core.h"

typedef struct {
    PyObject_HEAD
    PyObject *str;          /* original dep token string, used for __hash__/__eq__ */
    PyObject *cp;
    PyObject *cpv;
    PyObject *version;
    PyObject *operator;
    PyObject *blocker;
    PyObject *slot;
    PyObject *sub_slot;
    PyObject *slot_operator;
    PyObject *use;
} AtomObject;

/* Forward declaration so Atom_richcompare can reference AtomType. */
static PyTypeObject AtomType;

static void Atom_dealloc(AtomObject *self)
{
    Py_XDECREF(self->str);
    Py_XDECREF(self->cp);
    Py_XDECREF(self->cpv);
    Py_XDECREF(self->version);
    Py_XDECREF(self->operator);
    Py_XDECREF(self->blocker);
    Py_XDECREF(self->slot);
    Py_XDECREF(self->sub_slot);
    Py_XDECREF(self->slot_operator);
    Py_XDECREF(self->use);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *Atom_repr(AtomObject *self)
{
    return PyUnicode_FromFormat("Atom(%R)", self->str);
}

static PyObject *Atom_str(AtomObject *self)
{
    return Py_NewRef(self->str);
}

static Py_hash_t Atom_hash(AtomObject *self)
{
    return PyObject_Hash(self->str);
}

static PyObject *Atom_richcompare(AtomObject *self, PyObject *other, int op)
{
    if (op != Py_EQ && op != Py_NE)
        Py_RETURN_NOTIMPLEMENTED;

    if (Py_TYPE(other) != &AtomType) {
        if (op == Py_EQ) {
            Py_RETURN_FALSE;
        } else {
            Py_RETURN_TRUE;
        }
    }

    return PyObject_RichCompare(self->str, ((AtomObject *)other)->str, op);
}

#define ATOM_GETTER(field) \
    static PyObject *Atom_get_##field(AtomObject *self, UNUSED void *closure) \
    { return Py_NewRef(self->field); }

ATOM_GETTER(cp)
ATOM_GETTER(cpv)
ATOM_GETTER(version)
ATOM_GETTER(operator)
ATOM_GETTER(blocker)
ATOM_GETTER(slot)
ATOM_GETTER(sub_slot)
ATOM_GETTER(slot_operator)
ATOM_GETTER(use)

static PyGetSetDef Atom_getset[] = {
    { "cp",            (getter)Atom_get_cp,            NULL, NULL, NULL },
    { "cpv",           (getter)Atom_get_cpv,           NULL, NULL, NULL },
    { "version",       (getter)Atom_get_version,       NULL, NULL, NULL },
    { "operator",      (getter)Atom_get_operator,      NULL, NULL, NULL },
    { "blocker",       (getter)Atom_get_blocker,       NULL, NULL, NULL },
    { "slot",          (getter)Atom_get_slot,          NULL, NULL, NULL },
    { "sub_slot",      (getter)Atom_get_sub_slot,      NULL, NULL, NULL },
    { "slot_operator", (getter)Atom_get_slot_operator, NULL, NULL, NULL },
    { "use",           (getter)Atom_get_use,           NULL, NULL, NULL },
    { NULL }
};

static PyTypeObject AtomType = {
    .ob_base        = PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name        = "portage.dep._parser.Atom",
    .tp_basicsize   = sizeof(AtomObject),
    .tp_dealloc     = (destructor)Atom_dealloc,
    .tp_repr        = (reprfunc)Atom_repr,
    .tp_hash        = (hashfunc)Atom_hash,
    .tp_str         = (reprfunc)Atom_str,
    .tp_richcompare = (richcmpfunc)Atom_richcompare,
    .tp_flags       = Py_TPFLAGS_DEFAULT,
    .tp_getset      = Atom_getset,
};

/* Allocate an AtomObject and populate it.  Steals all refs.  Returns the
 * object, or NULL if the allocation failed (refs NOT consumed on NULL). */
static inline PyObject *atom_new(
    PyObject *str,
    PyObject *cp, PyObject *cpv, PyObject *version,
    PyObject *operator, PyObject *blocker,
    PyObject *slot, PyObject *sub_slot, PyObject *slot_operator,
    PyObject *use)
{
    AtomObject *obj = PyObject_New(AtomObject, &AtomType);

    if (!obj)
        return NULL;

    obj->str           = str;
    obj->cp            = cp;
    obj->cpv           = cpv;
    obj->version       = version;
    obj->operator      = operator;
    obj->blocker       = blocker;
    obj->slot          = slot;
    obj->sub_slot      = sub_slot;
    obj->slot_operator = slot_operator;
    obj->use           = use;

    return (PyObject *)obj;
}

/* Register AtomType with a module.  Call after PyType_Ready. */
static inline int atom_add_to_module(PyObject *m)
{
    return PyModule_AddType(m, &AtomType);
}

/* vim: set ts=4 sw=4 et: */
