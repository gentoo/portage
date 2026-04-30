# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

try:
    import liburing
except ImportError:
    liburing = None


class IoUring:
    """
    A high-level wrapper around the liburing-py library to facilitate
    asynchronous I/O operations using the Linux io_uring interface.
    """

    def __init__(self, entries=64):
        """
        Initialize the io_uring ring.

        @param entries: Number of entries in the submission queue.
        @type entries: int
        """
        if liburing is None:
            raise ImportError("liburing-py is required for io_uring support")
        self.ring = liburing.Ring(entries)
        # Pre-allocate a CQE object to reuse for completions
        self._cqe = liburing.Cqe()

    def close(self):
        """
        Shut down the io_uring ring and release kernel resources.
        """
        if hasattr(self, "ring"):
            self.ring.queue_exit()
            del self.ring

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def prep_read(self, fd, buffer, size, offset, user_data=0):
        """
        Prepare an asynchronous read operation.

        @param fd: File descriptor to read from.
        @param buffer: Buffer to read data into.
        @param size: Number of bytes to read.
        @param offset: File offset to start reading from.
        @param user_data: Identifier for the completion event.
        """
        sqe = liburing.io_uring_get_sqe(self.ring)
        if not sqe:
            self.submit()
            sqe = liburing.io_uring_get_sqe(self.ring)
        liburing.io_uring_prep_read(sqe, fd, buffer, size, offset)
        sqe.user_data = user_data

    def prep_write(self, fd, buffer, size, offset, user_data=0):
        """
        Prepare an asynchronous write operation.

        @param fd: File descriptor to write to.
        @param buffer: Buffer containing data to write.
        @param size: Number of bytes to write.
        @param offset: File offset to start writing at.
        @param user_data: Identifier for the completion event.
        """
        sqe = liburing.io_uring_get_sqe(self.ring)
        if not sqe:
            self.submit()
            sqe = liburing.io_uring_get_sqe(self.ring)
        liburing.io_uring_prep_write(sqe, fd, buffer, size, offset)
        sqe.user_data = user_data

    def prep_splice(
        self, fd_in, off_in, fd_out, off_out, nbytes, splice_flags, user_data=0
    ):
        """
        Prepare an asynchronous splice operation to move data between FDs
        without copying it into user-space memory.

        @param fd_in: Source file descriptor.
        @param off_in: Source offset (-1 for current pipe position).
        @param fd_out: Destination file descriptor.
        @param off_out: Destination offset (-1 for current pipe position).
        @param nbytes: Number of bytes to move.
        @param splice_flags: Flags controlling the splice (e.g., SPLICE_F_MOVE).
        @param user_data: Identifier for the completion event.
        """
        sqe = liburing.io_uring_get_sqe(self.ring)
        if not sqe:
            self.submit()
            sqe = liburing.io_uring_get_sqe(self.ring)
        liburing.io_uring_prep_splice(
            sqe, fd_in, off_in, fd_out, off_out, nbytes, splice_flags
        )
        sqe.user_data = user_data

    def prep_openat(self, dfd, path, flags, mode, user_data=0):
        """
        Prepare an asynchronous openat operation.

        @param dfd: Directory file descriptor (e.g., os.AT_FDCWD).
        @param path: Path to the file.
        @param flags: Open flags (e.g., os.O_RDONLY).
        @param mode: File mode if creating.
        @param user_data: Identifier for the completion event.
        """
        sqe = liburing.io_uring_get_sqe(self.ring)
        if not sqe:
            self.submit()
            sqe = liburing.io_uring_get_sqe(self.ring)
        liburing.io_uring_prep_openat(sqe, dfd, path, flags, mode)
        sqe.user_data = user_data

    def prep_close(self, fd, user_data=0):
        """
        Prepare an asynchronous close operation.

        @param fd: File descriptor to close.
        @param user_data: Identifier for the completion event.
        """
        sqe = liburing.io_uring_get_sqe(self.ring)
        if not sqe:
            self.submit()
            sqe = liburing.io_uring_get_sqe(self.ring)
        liburing.io_uring_prep_close(sqe, fd)
        sqe.user_data = user_data

    def prep_copy_file_range(
        self, fd_in, off_in, fd_out, off_out, nbytes, flags, user_data=0
    ):
        """
        Prepare an asynchronous copy_file_range operation.

        @param fd_in: Source file descriptor.
        @param off_in: Source offset.
        @param fd_out: Destination file descriptor.
        @param off_out: Destination offset.
        @param nbytes: Number of bytes to copy.
        @param flags: Flags (must be 0 for now).
        @param user_data: Identifier for the completion event.
        """
        sqe = liburing.io_uring_get_sqe(self.ring)
        if not sqe:
            self.submit()
            sqe = liburing.io_uring_get_sqe(self.ring)
        liburing.io_uring_prep_copy_file_range(
            sqe, fd_in, off_in, fd_out, off_out, nbytes, flags
        )
        sqe.user_data = user_data

    def submit(self):
        """
        Submit all prepared operations in the submission queue to the kernel.
        """
        return liburing.io_uring_submit(self.ring)

    def wait_cqe(self):
        """
        Wait for a completion event from the kernel.

        @return: A tuple (result, user_data) where result is the syscall
                 return value (>= 0 for success, < 0 for error).
        """
        liburing.io_uring_wait_cqe(self.ring, self._cqe)
        res = self._cqe.res
        user_data = self._cqe.user_data
        liburing.io_uring_cqe_seen(self.ring, self._cqe)
        return res, user_data


def is_available():
    """
    Check if io_uring support is available (liburing-py installed).
    """
    return liburing is not None
