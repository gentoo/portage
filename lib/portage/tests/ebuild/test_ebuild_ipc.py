# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import fcntl
import os
import shutil
import tempfile

from _emerge.EbuildIpcDaemon import EbuildIpcDaemon
from _emerge.SpawnProcess import SpawnProcess

from portage import _python_interpreter
from portage.const import PORTAGE_BIN_PATH
from portage.package.ebuild._ipc.IpcCommand import IpcCommand
from portage.tests import TestCase
from portage.util import ensure_dirs
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures import asyncio


class _ReplyCommand(IpcCommand):
    """Answer with a canned reply, whatever the arguments are."""

    __slots__ = ("reply",)

    def __init__(self, reply):
        IpcCommand.__init__(self)
        self.reply = reply

    def __call__(self, argv):
        return self.reply


class EbuildIpcTestCase(TestCase):
    """
    Exercise bin/ebuild-ipc.py against a real EbuildIpcDaemon.
    """

    _replies = (
        ("ascii", ("stdout\n", "stderr\n", 0)),
        ("non-ascii", ("Šťč\n", "äöü\n", 3)),
        # Larger than the pipe buffer, so the daemon needs more than one
        # write and the client more than one read.
        ("oversized", ("x" * 200000, "", 1)),
    )

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.event_loop = global_event_loop()
        self.env = {
            "PORTAGE_BUILDDIR": os.path.join(self.tmpdir, "cat", "pkg-1"),
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
        }
        for k in ("PORTAGE_USERNAME", "PORTAGE_GRPNAME", "PORTAGE_GID"):
            if k in os.environ:
                self.env[k] = os.environ[k]
        self._alive_fds = []

    def tearDown(self):
        for fd in self._alive_fds:
            os.close(fd)
        shutil.rmtree(self.tmpdir)

    def _alive_pipe(self, alive):
        """
        Return the read end of the pipe that tells the client whether the
        daemon is running, the way portage passes it to an ebuild.
        """
        read_fd, write_fd = os.pipe()
        self._alive_fds.append(read_fd)
        if alive:
            self._alive_fds.append(write_fd)
        else:
            os.close(write_fd)
        return read_fd

    def _start_client(self, env, args, alive_fd):
        """
        Start ebuild-ipc.py, and pass it alive_fd unless that is None,
        the way an older portage runs it. Return the process and a
        function that waits for it and returns its (returncode, stdout,
        stderr).
        """
        fd_pipes = {}
        if alive_fd is not None:
            env = {**env, "PORTAGE_IPC_ALIVE_FD": str(alive_fd)}
            fd_pipes[alive_fd] = alive_fd
        out_path = os.path.join(self.tmpdir, "stdout")
        err_path = os.path.join(self.tmpdir, "stderr")
        null_fd = os.open(os.devnull, os.O_RDONLY)
        out_fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        err_fd = os.open(err_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            proc = SpawnProcess(
                args=[
                    _python_interpreter,
                    "-E",
                    "-S",
                    "-X",
                    "utf8",
                    os.path.join(PORTAGE_BIN_PATH, "ebuild-ipc.py"),
                    *args,
                ],
                env=env,
                fd_pipes={0: null_fd, 1: out_fd, 2: err_fd, **fd_pipes},
                scheduler=self.event_loop,
            )
            proc.start()
        finally:
            for fd in (null_fd, out_fd, err_fd):
                os.close(fd)

        def wait():
            returncode = self.event_loop.run_until_complete(proc.async_wait())
            with open(out_path, encoding="utf-8") as f:
                stdout = f.read()
            with open(err_path, encoding="utf-8") as f:
                stderr = f.read()
            return returncode, stdout, stderr

        return proc, wait

    def _run_client(self, env, args, alive_fd):
        """
        Run ebuild-ipc.py and return its (returncode, stdout, stderr).
        """
        return self._start_client(env, args, alive_fd)[1]()

    def _make_fifos(self):
        ensure_dirs(os.path.join(self.env["PORTAGE_BUILDDIR"], ".ipc"))
        fifos = tuple(
            os.path.join(self.env["PORTAGE_BUILDDIR"], ".ipc", name)
            for name in ("in", "out")
        )
        for fifo in fifos:
            os.mkfifo(fifo)
        return fifos

    def _start_daemon(self, reply):
        input_fifo, output_fifo = (
            os.path.join(self.env["PORTAGE_BUILDDIR"], ".ipc", name)
            for name in ("in", "out")
        )
        daemon = EbuildIpcDaemon(
            commands={"test": _ReplyCommand(reply)},
            input_fifo=input_fifo,
            output_fifo=output_fifo,
            scheduler=self.event_loop,
        )
        daemon.start()
        return daemon

    def _stop_daemon(self, daemon):
        daemon.cancel()
        self.event_loop.run_until_complete(daemon.async_wait())

    def _lock_builddir_legacy(self):
        """
        Lock the build directory the way an older portage does while its
        daemon runs, and return the fd that holds the lock.
        """
        head, tail = os.path.split(self.env["PORTAGE_BUILDDIR"])
        fd = os.open(
            os.path.join(head, "." + tail + ".portage_lockfile"),
            os.O_CREAT | os.O_RDWR,
            0o660,
        )
        self._alive_fds.append(fd)
        fcntl.lockf(fd, fcntl.LOCK_EX)
        return fd

    def testReplies(self):
        self._make_fifos()
        alive_fd = self._alive_pipe(alive=True)
        for name, reply in self._replies:
            with self.subTest(reply=name):
                daemon = self._start_daemon(reply)
                try:
                    result = self._run_client(self.env, ["test"], alive_fd)
                finally:
                    self._stop_daemon(daemon)
                out, err, returncode = reply
                self.assertEqual(result, (returncode, out, err))

    def testLegacyReplies(self):
        # A portage that was already running when this one was installed
        # passes no PORTAGE_IPC_ALIVE_FD, and holds the build directory
        # lock instead.
        self._make_fifos()
        self._lock_builddir_legacy()
        for name, reply in self._replies:
            with self.subTest(reply=name):
                daemon = self._start_daemon(reply)
                try:
                    result = self._run_client(self.env, ["test"], None)
                finally:
                    self._stop_daemon(daemon)
                out, err, returncode = reply
                self.assertEqual(result, (returncode, out, err))

    def testLegacyNoDaemon(self):
        # Nobody holds the build directory lock, so an older portage has
        # no daemon running.
        ensure_dirs(os.path.join(self.env["PORTAGE_BUILDDIR"], ".ipc"))
        returncode, stdout, stderr = self._run_client(self.env, ["test"], None)
        self.assertEqual(returncode, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "ebuild-ipc: daemon process not detected\n")

    def testLegacyIpcLock(self):
        # An older daemon locks .ipc/lock with lockf() before it reopens
        # its fifo, and a client has to wait for it.
        self._make_fifos()
        self._lock_builddir_legacy()
        lock_file = os.path.join(self.env["PORTAGE_BUILDDIR"], ".ipc", "lock")
        lock_fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o660)
        fcntl.lockf(lock_fd, fcntl.LOCK_EX)
        reply = self._replies[0][1]
        daemon = self._start_daemon(reply)
        try:
            try:
                proc, wait = self._start_client(self.env, ["test"], None)
                self.event_loop.run_until_complete(asyncio.sleep(0.5))
                self.assertIsNone(proc.returncode)
            finally:
                # An older daemon unlinks the file when it releases it.
                os.unlink(lock_file)
                os.close(lock_fd)
            result = wait()
        finally:
            self._stop_daemon(daemon)
        out, err, returncode = reply
        self.assertEqual(result, (returncode, out, err))

    def testNoDaemon(self):
        # Portage closed its end of the pipe, so there is nothing left to
        # answer and the client must say so rather than wait.
        ensure_dirs(os.path.join(self.env["PORTAGE_BUILDDIR"], ".ipc"))
        returncode, stdout, stderr = self._run_client(
            self.env, ["test"], self._alive_pipe(alive=False)
        )
        self.assertEqual(returncode, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "ebuild-ipc: daemon process not detected\n")
