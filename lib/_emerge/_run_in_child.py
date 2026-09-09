# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""
Support for running a function in a child process and returning the value
it produced.
"""

import os
import pickle
import signal
import socket
import sys
import traceback

import portage
from portage.util._eventloop.global_event_loop import global_event_loop

_RECV_CHUNK_SIZE = 1 << 20
_LENGTH_BYTES = 8

# Sent by the child once it owns stdio, so that the parent knows whether a
# later failure may be retried in process. See run_in_child().
_CHILD_READY = b"\x01"


class ForkFailed(Exception):
    """
    The child never reached target(), so it has shown no output and asked
    nothing, and the caller may call target() in the current process. It
    may have printed a traceback for the failure itself.
    """


class ChildFailed(Exception):
    """
    The child reached target() and then failed. It may already have written
    output or prompted the user, so the caller must not call target() again,
    because that would repeat all of it.

    The exit_code attribute is what the caller should exit with, which
    carries a signal that killed the child, so that an interrupted prompt
    reports as an interrupt rather than as a failure.
    """

    def __init__(self, message, exit_code=1):
        super().__init__(message)
        self.exit_code = exit_code


class _TransferError(Exception):
    """
    A result could not be read from the child. run_in_child() turns this
    into ForkFailed or ChildFailed, depending on how far the child got.
    """


def _send(sock, payload):
    blob = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    sock.sendall(len(blob).to_bytes(_LENGTH_BYTES, "little"))
    sock.sendall(blob)


def _recv_exact(sock, size):
    """
    Read exactly size bytes, or return None if the peer closed first.
    """
    chunks = []
    received = 0
    while received < size:
        chunk = sock.recv(min(_RECV_CHUNK_SIZE, size - received))
        if not chunk:
            return None
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


def _recv(sock):
    header = _recv_exact(sock, _LENGTH_BYTES)
    if header is None:
        raise _TransferError("the child exited without sending a result")

    blob = _recv_exact(sock, int.from_bytes(header, "little"))
    if blob is None:
        raise _TransferError("the child exited while sending its result")

    try:
        return pickle.loads(blob)
    except Exception as e:
        raise _TransferError(f"malformed result from the child: {e}") from e


def _child_setup():
    """
    Put the child in the state that portage expects of a forked process.

    This is ForkProcess._bootstrap() less the SIGINT and SIGTERM handlers,
    which the child keeps because it owns the terminal and may run a prompt,
    so an interrupt has to behave as it does in the parent.
    """
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    try:
        wakeup_fd = signal.set_wakeup_fd(-1)
        if wakeup_fd > 0:
            os.close(wakeup_fd)
    except (ValueError, OSError):
        pass

    portage.locks._close_fds()
    portage.process.spawned_pids = []


def _child_exit_hooks():
    """
    Run the exit hooks which the child registered, since os._exit() will not.

    run_exitfuncs() skips the hooks that were registered before the fork (see
    bug 937891), and never sees a coroutine hook, which atexit_register() puts
    on the event loop for close() to run.
    """
    try:
        loop = global_event_loop(create=False)
        if loop is not None:
            loop.close()
    except BaseException:
        traceback.print_exc()

    try:
        portage.process.run_exitfuncs()
    except BaseException:
        traceback.print_exc()


def _run_in_child(parent_sock, child_sock, target):
    """
    Run target() in the child process that run_in_child() forks, and report
    the result over child_sock.

    This is the target of the portage.process._start_fork() call in
    run_in_child(), and always exits via os._exit(), so that _start_fork()'s
    own exit-in-finally (see bug #345289) never runs after us.
    """
    status = 1
    try:
        parent_sock.close()
        _child_setup()
        # Everything from here on may write to the inherited stdio, so
        # tell the parent that a failure is no longer safe to retry.
        child_sock.sendall(_CHILD_READY)
        _send(child_sock, target())
        status = 0
    except SystemExit as e:
        # UserQuery.query() exits this way when a prompt is interrupted.
        status = e.code if isinstance(e.code, int) else int(e.code is not None)
    except KeyboardInterrupt:
        status = 128 + signal.SIGINT
    except BaseException:
        traceback.print_exc()
    finally:
        _child_exit_hooks()
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            child_sock.close()
        except BaseException:
            pass
        os._exit(status)


def run_in_child(target):
    """
    Call target() in a child process and return the value it produced.

    The value must be picklable. The child inherits stdio, so anything the
    target displays (or asks the user) behaves as it does in process.

    @raise ForkFailed: the child never reached target(), and the caller may
            call it in this process instead.
    @raise ChildFailed: the child reached target() and then failed. It may
            have displayed output or prompted the user, so the caller must
            not call target() again. Its exit_code attribute carries the
            status of the child, so that an interrupt stays an interrupt.
    """
    try:
        parent_sock, child_sock = socket.socketpair()
    except OSError as e:
        raise ForkFailed(f"socketpair failed: {e}") from e

    sys.stdout.flush()
    sys.stderr.flush()

    try:
        pid = portage.process._start_fork(
            _run_in_child,
            args=(parent_sock, child_sock, target),
            fd_pipes=None,
            close_fds=False,
        )
    except OSError as e:
        parent_sock.close()
        child_sock.close()
        raise ForkFailed(f"fork failed: {e}") from e

    child_sock.close()
    started = False
    try:
        try:
            started = _recv_exact(parent_sock, len(_CHILD_READY)) == _CHILD_READY
            if not started:
                raise _TransferError("the child exited before it started")
            payload = _recv(parent_sock)
        finally:
            parent_sock.close()
    except _TransferError as e:
        message = str(e)
    except KeyboardInterrupt:
        # The same signal reached the child, which is where target() or a
        # prompt it ran was interrupted, so let its status say so.
        message = "the child was interrupted"
    except Exception as e:
        message = f"could not read the result from the child: {e}"
    except BaseException:
        # Reap the child rather than leaving it behind.
        _wait(pid)
        raise
    else:
        status = _wait(pid)
        if status not in (0, None):
            raise ChildFailed(
                f"the child exited with status {status}", exit_code=status
            )
        return payload

    status = _wait(pid)
    if started:
        raise ChildFailed(message, exit_code=status or 1) from None
    raise ForkFailed(message) from None


def _wait(pid):
    """
    Reap pid and return its exit status, or None if it was reaped elsewhere.
    """
    while True:
        try:
            _, status = os.waitpid(pid, 0)
        except InterruptedError:
            continue
        except ChildProcessError:
            return None
        if os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        if os.WIFSIGNALED(status):
            return 128 + os.WTERMSIG(status)
        return 1
