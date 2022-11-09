/* Copyright 2005-2020 Gentoo Authors
 * Distributed under the terms of the GNU General Public License v2
 */

#include <Python.h>
#include <stdlib.h>
#include <ctype.h>

static PyObject * _libc_tolower(PyObject *, PyObject *);
static PyObject * _libc_toupper(PyObject *, PyObject *);

static PyMethodDef LibcMethods[] = {
	{
		.ml_name = "tolower",
		.ml_meth = _libc_tolower,
		.ml_flags = METH_VARARGS,
		.ml_doc = "Convert to lower case using system locale."

	},
	{
		.ml_name = "toupper",
		.ml_meth = _libc_toupper,
		.ml_flags = METH_VARARGS,
		.ml_doc = "Convert to upper case using system locale."
	},
	{NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
	PyModuleDef_HEAD_INIT,
	.m_name = "libc",
	.m_doc = "Module for converting case using the system locale",
	.m_size = -1,
	.m_methods = LibcMethods,
};

PyMODINIT_FUNC
PyInit_libc(void)
{
	PyObject *m;
	m = PyModule_Create(&moduledef);
	return m;
}


static PyObject *
_libc_tolower(PyObject *self, PyObject *args)
{
	int c;

	if (!PyArg_ParseTuple(args, "i", &c))
		return NULL;

	return Py_BuildValue("i", tolower(c));
}


static PyObject *
_libc_toupper(PyObject *self, PyObject *args)
{
	int c;

	if (!PyArg_ParseTuple(args, "i", &c))
		return NULL;

	return Py_BuildValue("i", toupper(c));
}
