# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import fcntl
import logging
import os
import platform
import shutil
import sys


logger = logging.getLogger(__name__)

# Added in Python 3.12
FICLONE = getattr(fcntl, "FICLONE", 0x40049409)

# Unavailable in PyPy
SEEK_DATA = getattr(os, "SEEK_DATA", 3)
SEEK_HOLE = getattr(os, "SEEK_HOLE", 4)


def _get_chunks(src):
    try:
        offset_hole = 0
        while True:
            try:
                # Find the next bit of data
                offset_data = os.lseek(src, offset_hole, SEEK_DATA)
            except OSError as e:
                # Re-raise for unexpected errno values
                if e.errno not in (errno.EINVAL, errno.ENXIO):
                    raise

                offset_end = os.lseek(src, 0, os.SEEK_END)

                if e.errno == errno.ENXIO:
                    # End of file
                    if offset_end > offset_hole:
                        # Hole at end of file
                        yield (offset_end, 0)
                else:
                    # SEEK_DATA failed with EINVAL, return the whole file
                    yield (0, offset_end)

                break
            else:
                offset_hole = os.lseek(src, offset_data, SEEK_HOLE)
                yield (offset_data, offset_hole - offset_data)

    except OSError:
        logger.warning("_get_chunks failed unexpectedly", exc_info=sys.exc_info())
        raise


def _do_copy_file_range(src, dst, offset, count):
    while count > 0:
        # count must fit in ssize_t
        c = min(count, sys.maxsize)
        written = os.copy_file_range(src, dst, c, offset, offset)
        if written == 0:
            # https://bugs.gentoo.org/828844
            raise OSError(errno.EOPNOTSUPP, os.strerror(errno.EOPNOTSUPP))
        offset += written
        count -= written


def _do_sendfile(src, dst, offset, count):
    os.lseek(dst, offset, os.SEEK_SET)
    while count > 0:
        # count must fit in ssize_t
        c = min(count, sys.maxsize)
        written = os.sendfile(dst, src, offset, c)
        offset += written
        count -= written


def _fastcopy(src, dst):
    with (
        open(src, "rb", buffering=0) as srcf,
        open(dst, "wb", buffering=0) as dstf,
    ):
        srcfd = srcf.fileno()
        dstfd = dstf.fileno()

        if platform.system() == "Linux":
            try:
                fcntl.ioctl(dstfd, FICLONE, srcfd)
                return
            except OSError:
                pass

        try_cfr = hasattr(os, "copy_file_range")

        for offset, count in _get_chunks(srcfd):
            if count == 0:
                os.ftruncate(dstfd, offset)
            else:
                if try_cfr:
                    try:
                        _do_copy_file_range(srcfd, dstfd, offset, count)
                        continue
                    except OSError as e:
                        try_cfr = False
                        if e.errno not in (errno.EXDEV, errno.ENOSYS, errno.EOPNOTSUPP):
                            logger.warning(
                                "_do_copy_file_range failed unexpectedly",
                                exc_info=sys.exc_info(),
                            )
                try:
                    _do_sendfile(srcfd, dstfd, offset, count)
                except OSError:
                    logger.warning(
                        "_do_sendfile failed unexpectedly", exc_info=sys.exc_info()
                    )
                    raise


def copyfile(src, dst):
    """
    Copy the contents (no metadata) of the file named src to a file
    named dst.

    If possible, copying is done within the kernel, and uses
    "copy acceleration" techniques (such as reflinks). This also
    supports sparse files.

    @param src: path of source file
    @type src: str
    @param dst: path of destination file
    @type dst: str
    """

    try:
        _fastcopy(src, dst)
    except OSError:
        shutil.copyfile(src, dst)
