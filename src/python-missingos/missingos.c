/* $Id$ */

#include "Python.h"

#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

static char missingos_lchown__doc__[];
static PyObject * missingos_lchown(PyObject *self, PyObject *args);
static char missingos_mknod__doc__[];
static PyObject * missingos_mknod(PyObject *self, PyObject *args);

static char missingos__doc__[] = "Provide some operations that\
    are missing from the standard os / posix modules.";

static PyMethodDef missingos_methods[] = {
    {"lchown", missingos_lchown, METH_VARARGS, missingos_lchown__doc__},
    {"mknod", missingos_mknod, METH_VARARGS, missingos_mknod__doc__},
    {NULL,		NULL}		/* sentinel */
};

static PyObject *
posix_error_with_allocated_filename(char* name)
{
    PyObject *rc = PyErr_SetFromErrnoWithFilename(PyExc_OSError, name);
    PyMem_Free(name);
    return rc;
}

static char missingos_lchown__doc__[] =
"lchown(path, uid, gid) -> None\n\
Change the owner and group id of path to the numeric uid and gid.";

static PyObject *
missingos_lchown(PyObject *self, PyObject *args) {
    char *path = NULL;
    int uid, gid;
    int res;
    if (!PyArg_ParseTuple(args, "etii:lchown",
                          Py_FileSystemDefaultEncoding, &path,
                          &uid, &gid))
        return NULL;
    res = lchown(path, (uid_t) uid, (gid_t) gid);
    if (res < 0)
        return posix_error_with_allocated_filename(path);
    PyMem_Free(path);
    Py_INCREF(Py_None);
    return Py_None;
}

static char missingos_mknod__doc__[] =
"mknod(path, type, major, minor [, mode=0600 ]) -> None\n\
Create a special file. Mode fixed at 0600.\
Note that for type 'p' major and minor are ignored.\
";

static PyObject *
missingos_mknod(PyObject *self, PyObject *args) {
    char *path = NULL;
    char *type = NULL;
    int major = 0;
    int minor = 0;
    mode_t real_mode;
    dev_t real_dev;
    int mode = 0600;

    int res;
    if (!PyArg_ParseTuple(args, "etsii|i:mknod",
                          Py_FileSystemDefaultEncoding, &path,
                          &type, &major, &minor, &mode))
        return NULL;
    /* type can be *one* of b, c, u, p */
    /* major/minor are forbidden for p, reqd otherwise */
    if (!strcmp(type, "p")) {
        /* pipe */
        if (major != 0 || minor != 0) {
            return NULL;
        }
        real_mode = S_IFIFO;
        major = 0;
        minor = 0;
    } else if (!strcmp(type, "b")) {
        /* block */
        real_mode = S_IFBLK;
    } else if (!strcmp(type, "c")) {
        real_mode = S_IFCHR;
        /* char */
    } else if (!strcmp(type, "u")) {
        real_mode = S_IFCHR;
        /* unbuffered char */
    } else {
        /* error */
        PyErr_SetString(PyExc_ValueError, "type must be one of p,b,c,u");
        return NULL;
    }

    real_mode |= mode;
    real_dev = (major << 8) | minor;

    /* use mode to modify real_mode */

    res = mknod(path, real_mode, real_dev);
    if (res < 0)
        return posix_error_with_allocated_filename(path);
    PyMem_Free(path);
    Py_INCREF(Py_None);
    return Py_None;
}


DL_EXPORT(void)
initmissingos(void) {
    PyObject *m;

    m = Py_InitModule4("missingos", missingos_methods,
                       missingos__doc__, (PyObject *)NULL,
                       PYTHON_API_VERSION);
}
