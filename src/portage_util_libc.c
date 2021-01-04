/* Copyright 2005-2020 Gentoo Authors
 * Distributed under the terms of the GNU General Public License v2
 */

#include <Python.h>
#include <stdlib.h>
#include <ctype.h>

static PyObject * _libc_tolower(PyObject *, PyObject *);
static PyObject * _libc_toupper(PyObject *, PyObject *);

static PyMethodDef LibcMethods[] = {
	{"tolower", _libc_tolower, METH_VARARGS, "Convert to lower case using system locale."},
	{"toupper", _libc_toupper, METH_VARARGS, "Convert to upper case using system locale."},
	{NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
	PyModuleDef_HEAD_INIT,
	"libc",								/* m_name */
	"Module for converting case using the system locale",		/* m_doc */
	-1,								/* m_size */
	LibcMethods,							/* m_methods */
	NULL,								/* m_reload */
	NULL,								/* m_traverse */
	NULL,								/* m_clear */
	NULL,								/* m_free */
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
