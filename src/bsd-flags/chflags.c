/* $Id$ */

#include "Python.h"

#include <sys/stat.h>

static char chflags_lchflags__doc__[];
static PyObject * chflags_lchflags(PyObject *self, PyObject *args);
static char chflags_lgetflags__doc__[];
static PyObject * chflags_lgetflags(PyObject *self, PyObject *args);
static char chflags_lhasproblems__doc__[];
static PyObject * chflags_lhasproblems(PyObject *self, PyObject *args);

static char chflags__doc__[] = "Provide some operations for manipulating" \
	"FreeBSD's filesystem flags";

static PyMethodDef chflags_methods[] = {
	{"lchflags", chflags_lchflags, METH_VARARGS, chflags_lchflags__doc__},
	{"lgetflags", chflags_lgetflags, METH_VARARGS, chflags_lgetflags__doc__},
	{"lhasproblems", chflags_lhasproblems, METH_VARARGS, chflags_lhasproblems__doc__},
	{NULL, NULL}
};

static char chflags_lchflags__doc__[] = 
"lchflags(path, flags) -> None\n\
Change the flags on path to equal flags.";

static char chflags_lgetflags__doc__[] =
"lgetflags(path) -> Integer\n\
Returns the file flags on path.";

static char chflags_lhasproblems__doc__[] = 
"lhasproblems(path) -> Integer\n\
Returns 1 if path has any flags set that prevent write operations;\n\
0 otherwise.";

static const unsigned long problemflags=0x00160016;

#if defined __FreeBSD__
static PyObject *chflags_lchflags(PyObject *self, PyObject *args) 
{
	char *path = NULL;
	int flags;
	int res;

	if (!PyArg_ParseTuple(args, "eti:lchflags",
			      Py_FileSystemDefaultEncoding, &path,
			      &flags))
	{
		return NULL;
	}

	res = lchflags(path, flags);

	PyMem_Free(path);
	return PyInt_FromLong((long)res);
}

static PyObject *chflags_lhasproblems(PyObject *self, PyObject *args)
{
	char *path = NULL;
	struct stat sb;
	int res;

	if (!PyArg_ParseTuple(args, "et:lhasproblems",
				Py_FileSystemDefaultEncoding, &path))
	{
		return NULL;
	}

	res = lstat(path, &sb);

	PyMem_Free(path);
		
	if (res < 0)
	{
		return PyInt_FromLong((long)res);
	}

	if (sb.st_flags & problemflags)
		return PyInt_FromLong(1);
	else
		return PyInt_FromLong(0);
}

static PyObject *chflags_lgetflags(PyObject *self, PyObject *args)
{
	char *path = NULL;
	struct stat sb;
	int res;

	if (!PyArg_ParseTuple(args, "et:lgetflags",
			      Py_FileSystemDefaultEncoding, &path))
	{
		return NULL;
	}

	res = lstat(path, &sb);

	if (res < 0)
	{
		PyMem_Free(path);
		return PyInt_FromLong((long)res);
	}

	PyMem_Free(path);

	return PyInt_FromLong((long)sb.st_flags);
}

#else
#warning Not on FreeBSD; building dummy lchflags

static PyObject *chflags_lgetflags(PyObject *self, PyObject *args)
{
	/* Obviously we can't set flags if the OS/filesystem doesn't support them. */
	return PyInt_FromLong(0);
}

static PyObject *chflags_lchflags(PyObject *self, PyObject *args)
{
	/* If file system flags aren't supported, just return 0,
	 as the effect is basically the same. */
	return PyInt_FromLong(0);
}

static PyObject *chflags_lhasproblems(PyObject *self, PyObject *args)
{
	return PyInt_FromLong(0);
}

#endif

static int ins(PyObject *m, char *symbolname, int value)
{
	return PyModule_AddIntConstant(m, symbolname, value);
}

DL_EXPORT(void) initchflags(void)
{
	PyObject *m;
	m = Py_InitModule4("chflags", chflags_methods, chflags__doc__,
			   (PyObject*)NULL, PYTHON_API_VERSION);
	
	ins(m, "UF_SETTABLE",  0x0000ffff);
	ins(m, "UF_NODUMP",    0x00000001);
	ins(m, "UF_IMMUTABLE", 0x00000002);
	ins(m, "UF_APPEND",    0x00000004);
	ins(m, "UF_OPAQUE",    0x00000008);
	ins(m, "UF_NOUNLINK",  0x00000010);

	ins(m, "SF_SETTABLE",  0xffff0000);
	ins(m, "SF_NODUMP",    0x00010000);
	ins(m, "SF_IMMUTABLE", 0x00020000);
	ins(m, "SF_APPEND",    0x00040000);
	ins(m, "SF_OPAQUE",    0x00080000);
	ins(m, "SF_NOUNLINK",  0x00100000);
	ins(m, "SF_SNAPSHOT",  0x00200000);

	ins(m, "PROBLEM_FLAGS", 0x00160016);
}
