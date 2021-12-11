/* Copyright 2017-2020 Gentoo Authors
 * Distributed under the terms of the GNU General Public License v2
 */

#include <Python.h>
#include <errno.h>
#include <stdlib.h>
#include <ctype.h>
#include <sys/sendfile.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>

static PyObject * _reflink_linux_file_copy(PyObject *, PyObject *);

static PyMethodDef reflink_linuxMethods[] = {
    {
            "file_copy",
            _reflink_linux_file_copy,
            METH_VARARGS,
            "Copy between two file descriptors, "
            "with reflink and sparse file support."
    },
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "reflink_linux",                                /* m_name */
    "Module for reflink_linux copy operations",     /* m_doc */
    -1,                                             /* m_size */
    reflink_linuxMethods,                           /* m_methods */
    NULL,                                           /* m_reload */
    NULL,                                           /* m_traverse */
    NULL,                                           /* m_clear */
    NULL,                                           /* m_free */
};

PyMODINIT_FUNC
PyInit_reflink_linux(void)
{
    PyObject *m;
    m = PyModule_Create(&moduledef);
    return m;
}


/**
 * cfr_wrapper - A copy_file_range syscall wrapper function, having a
 * function signature that is compatible with sf_wrapper.
 * @fd_out: output file descriptor
 * @fd_in: input file descriptor
 * @off_out: must point to a buffer that specifies the starting offset
 * where bytes will be copied to fd_out, and this buffer is adjusted by
 * the number of bytes copied.
 * @len: number of bytes to copy between the file descriptors
 *
 * Bytes are copied from fd_in starting from *off_out, and the file
 * offset of fd_in is not changed. Effects on the file offset of
 * fd_out are undefined.
 *
 * Return: Number of bytes written to out_fd on success, -1 on failure
 * (errno is set appropriately).
 */
static ssize_t
cfr_wrapper(int fd_out, int fd_in, off_t *off_out, size_t len)
{
#ifdef __NR_copy_file_range
    off_t off_in = *off_out;
    return syscall(__NR_copy_file_range, fd_in, &off_in, fd_out,
                   off_out, len, 0);
#else
    /* This is how it fails at runtime when the syscall is not supported. */
    errno = ENOSYS;
    return -1;
#endif
}

/**
 * sf_wrapper - A sendfile wrapper function, having a function signature
 * that is compatible with cfr_wrapper.
 * @fd_out: output file descriptor
 * @fd_in: input file descriptor
 * @off_out: must point to a buffer that specifies the starting offset
 * where bytes will be copied to fd_out, and this buffer is adjusted by
 * the number of bytes copied.
 * @len: number of bytes to copy between the file descriptors
 *
 * Bytes are copied from fd_in starting from *off_out, and the file
 * offset of fd_in is not changed. Effects on the file offset of
 * fd_out are undefined.
 *
 * Return: Number of bytes written to out_fd on success, -1 on failure
 * (errno is set appropriately).
 */
static ssize_t
sf_wrapper(int fd_out, int fd_in, off_t *off_out, size_t len)
{
    ssize_t ret;
    off_t off_in = *off_out;
    /* The sendfile docs do not specify behavior of the output file
     * offset, therefore it must be adjusted with lseek.
     */
    if (lseek(fd_out, *off_out, SEEK_SET) < 0)
        return -1;
    ret = sendfile(fd_out, fd_in, &off_in, len);
    if (ret > 0)
        *off_out += ret;
    return ret;
}


/**
 * do_lseek_data - Adjust file offsets to the next location containing
 * data, creating sparse empty blocks in the output file as needed.
 * @fd_in: input file descriptor
 * @fd_out: output file descriptor
 * @off_out: offset of the output file
 *
 * Use lseek SEEK_DATA to adjust off_out to the next location from fd_in
 * containing data (creates sparse empty blocks when appropriate). Effects
 * on file offsets are undefined.
 *
 * Return: On success, the number of bytes to copy before the next hole,
 * and -1 on failure (errno is set appropriately). Returns 0 when fd_in
 * reaches EOF.
 */
static off_t
do_lseek_data(int fd_out, int fd_in, off_t *off_out) {
#ifdef SEEK_DATA
    /* Use lseek SEEK_DATA/SEEK_HOLE for sparse file support,
     * as suggested in the copy_file_range man page.
     */
    off_t offset_data, offset_hole;

    offset_data = lseek(fd_in, *off_out, SEEK_DATA);
    if (offset_data < 0) {
        if (errno == ENXIO) {
            /* EOF - If the file ends with a hole, then use lseek SEEK_END
             * to find the end offset, and create sparse empty blocks in
             * the output file. It's the caller's responsibility to
             * truncate the file.
             */
            offset_hole = lseek(fd_in, 0, SEEK_END);
            if (offset_hole < 0) {
                return -1;
            } else if (offset_hole != *off_out) {
                if (lseek(fd_out, offset_hole, SEEK_SET) < 0) {
                    return -1;
                }
                *off_out = offset_hole;
            }
            return 0;
        }
        return -1;
    }

    /* Create sparse empty blocks in the output file, up
     * until the next location that will contain data.
     */
    if (offset_data != *off_out) {
        if (lseek(fd_out, offset_data, SEEK_SET) < 0) {
            return -1;
        }
        *off_out = offset_data;
    }

    /* Locate the next hole, so that we know when to
     * stop copying. There is an implicit hole at the
     * end of the file. This should never result in ENXIO
     * after SEEK_DATA has succeeded above.
     */
    offset_hole = lseek(fd_in, offset_data, SEEK_HOLE);
    if (offset_hole < 0) {
        return -1;
    }

    return offset_hole - offset_data;
#else
    /* This is how it fails at runtime when lseek SEEK_DATA is not supported. */
    errno = EINVAL;
    return -1;
#endif
}


/**
 * _reflink_linux_file_copy - Copy between two file descriptors, with
 * reflink and sparse file support.
 * @fd_in: input file descriptor
 * @fd_out: output file descriptor
 *
 * When supported, this uses copy_file_range for reflink support,
 * and lseek SEEK_DATA for sparse file support. It has graceful
 * fallbacks when support is unavailable for copy_file_range, lseek
 * SEEK_DATA, or sendfile operations. When all else fails, it uses
 * a plain read/write loop that works in any kernel version.
 *
 * If a syscall is interrupted by a signal, then the function will
 * automatically resume copying a the appropriate location which is
 * tracked internally by the offset_out variable.
 * 
 * Return: The length of the output file on success. Raise OSError
 * on failure.
 */
static PyObject *
_reflink_linux_file_copy(PyObject *self, PyObject *args)
{
    int eintr_retry, error, fd_in, fd_out, stat_in_acquired, stat_out_acquired;
    int lseek_works, sendfile_works;
    off_t offset_out, len;
    ssize_t buf_bytes, buf_offset, copyfunc_ret;
    struct stat stat_in, stat_out;
    char* buf;
    ssize_t (*copyfunc)(int, int, off_t *, size_t);

    if (!PyArg_ParseTuple(args, "ii", &fd_in, &fd_out))
        return NULL;

    eintr_retry = 1;
    offset_out = 0;
    stat_in_acquired = 0;
    stat_out_acquired = 0;
    buf = NULL;
    buf_bytes = 0;
    buf_offset = 0;
    copyfunc = cfr_wrapper;
    lseek_works = 1;
    sendfile_works = 1;

    while (eintr_retry) {

        Py_BEGIN_ALLOW_THREADS

        /* Linux 3.1 and later support SEEK_DATA (for sparse file support).
         * This code uses copy_file_range if possible, and falls back to
         * sendfile for cross-device or when the copy_file_range syscall
         * is not available (less than Linux 4.5). This will fail for
         * Linux less than 3.1, which does not support the lseek SEEK_DATA
         * parameter.
         */
        if (sendfile_works && lseek_works) {
            error = 0;

            while (1) {
                len = do_lseek_data(fd_out, fd_in, &offset_out);
                if (!len) {
                    /* EOF */
                    break;
                } else if (len < 0) {
                    error = errno;
                    if ((errno == EINVAL || errno == EOPNOTSUPP) && !offset_out) {
                        lseek_works = 0;
                    }
                    break;
                }

                copyfunc_ret = copyfunc(fd_out,
                                        fd_in,
                                        &offset_out,
                                        len);

                if (copyfunc_ret <= 0) {
                    error = errno;
                    if ((errno == EXDEV || errno == ENOSYS || errno == EOPNOTSUPP || copyfunc_ret == 0) &&
                        copyfunc == cfr_wrapper) {
                        /* Use sendfile instead of copy_file_range for
                         * cross-device copies, or when the copy_file_range
                         * syscall is not available (less than Linux 4.5),
                         * or when copy_file_range copies zero bytes.
                         */
                        error = 0;
                        copyfunc = sf_wrapper;
                        copyfunc_ret = copyfunc(fd_out,
                                                fd_in,
                                                &offset_out,
                                                len);

                        if (copyfunc_ret < 0) {
                            error = errno;
                            /* On Linux, if lseek succeeded above, then
                             * sendfile should have worked here too, so
                             * don't bother to fallback for EINVAL here.
                             */
                            break;
                        }
                    } else {
                        break;
                    }
                }
            }
        }

        /* Less than Linux 3.1 does not support SEEK_DATA or copy_file_range,
         * so just use sendfile for in-kernel copy. This will fail for Linux
         * versions from 2.6.0 to 2.6.32, because sendfile does not support
         * writing to regular files.
         */
        if (sendfile_works && !lseek_works) {
            error = 0;

            if (!stat_in_acquired && fstat(fd_in, &stat_in) < 0) {
                error = errno;
            } else {
                stat_in_acquired = 1;

                while (offset_out < stat_in.st_size) {
                    copyfunc_ret = sf_wrapper(fd_out,
                                              fd_in,
                                              &offset_out,
                                              stat_in.st_size - offset_out);

                    if (copyfunc_ret < 0) {
                        error = errno;
                        if (errno == EINVAL && !offset_out) {
                            sendfile_works = 0;
                        }
                        break;
                    }
                }
            }
        }

        /* This implementation will work on any kernel. */
        if (!sendfile_works) {
            error = 0;

            if (!stat_out_acquired && fstat(fd_in, &stat_out) < 0) {
                error = errno;
            } else {
                stat_out_acquired = 1;
                if (buf == NULL)
                    buf = malloc(stat_out.st_blksize);
                if (buf == NULL) {
                    error = errno;

                /* For the read call, the fd_in file offset must be exactly
                 * equal to offset_out + buf_bytes, where buf_bytes is the
                 * amount of buffered data that has not been written to
                 * to the output file yet. Use lseek to ensure correct state,
                 * in case an EINTR retry caused it to get out of sync
                 * somewhow.
                 */
                } else if (lseek(fd_in, offset_out + buf_bytes, SEEK_SET) < 0) {
                    error = errno;
                } else {
                    while (1) {
                        /* Some bytes may still be buffered from the
                         * previous iteration of the outer loop.
                         */
                        if (!buf_bytes) {
                            buf_offset = 0;
                            buf_bytes = read(fd_in, buf, stat_out.st_blksize);

                            if (!buf_bytes) {
                                /* EOF */
                                break;

                            } else if (buf_bytes < 0) {
                                error = errno;
                                buf_bytes = 0;
                                break;
                            }
                        }

                        copyfunc_ret = write(fd_out,
                                             buf + buf_offset,
                                             buf_bytes);

                        if (copyfunc_ret < 0) {
                            error = errno;
                            break;
                        }

                        buf_bytes -= copyfunc_ret;
                        buf_offset += copyfunc_ret;
                        offset_out += copyfunc_ret;
                    }
                }
            }
        }

        if (!error && ftruncate(fd_out, offset_out) < 0)
            error = errno;

        Py_END_ALLOW_THREADS

        if (!(error == EINTR && PyErr_CheckSignals() == 0))
            eintr_retry = 0;
    }

    if (buf != NULL)
        free(buf);

    if (error)
        return PyErr_SetFromErrno(PyExc_OSError);

    return Py_BuildValue("i", offset_out);
}
