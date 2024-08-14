# portage.py -- core Portage functionality
# Copyright 1998-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2


import asyncio as _asyncio
import atexit
import errno
import fcntl
import io
import logging
import multiprocessing
import platform
import signal
import socket
import subprocess
import sys
import traceback
import os as _os
import warnings

from dataclasses import dataclass
from functools import lru_cache, partial
from typing import Any, Optional, Callable, Union

from portage import os
from portage import _encodings
from portage import _unicode_encode
import portage

portage.proxy.lazyimport.lazyimport(
    globals(),
    "portage.util._async.ForkProcess:ForkProcess",
    "portage.util._eventloop.global_event_loop:global_event_loop",
    "portage.util.futures:asyncio",
    "portage.util:dump_traceback,writemsg,writemsg_level",
)

from portage.const import BASH_BINARY, SANDBOX_BINARY, FAKEROOT_BINARY
from portage.exception import CommandNotFound
from portage.proxy.objectproxy import ObjectProxy
from portage.util._ctypes import load_libc, LoadLibrary, ctypes

try:
    from portage.util.netlink import RtNetlink
except ImportError:
    if platform.system() == "Linux":
        raise
    RtNetlink = None

try:
    import resource

    max_fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
except ImportError:
    max_fd_limit = 256


# Support PEP 446 for Python >=3.4
try:
    _set_inheritable = _os.set_inheritable
except AttributeError:
    _set_inheritable = None

try:
    _FD_CLOEXEC = fcntl.FD_CLOEXEC
except AttributeError:
    _FD_CLOEXEC = None

# Prefer /proc/self/fd if available (/dev/fd
# doesn't work on solaris, see bug #474536).
for _fd_dir in ("/proc/self/fd", "/dev/fd"):
    if os.path.isdir(_fd_dir):
        break
    else:
        _fd_dir = None

# /dev/fd does not work on FreeBSD, see bug #478446
if platform.system() in ("FreeBSD",) and _fd_dir == "/dev/fd":
    _fd_dir = None

if _fd_dir is not None:

    def get_open_fds():
        return (int(fd) for fd in os.listdir(_fd_dir) if fd.isdigit())

    if platform.python_implementation() == "PyPy":
        # EAGAIN observed with PyPy 1.8.
        _get_open_fds = get_open_fds

        def get_open_fds():
            try:
                return _get_open_fds()
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    raise
                return range(max_fd_limit)

elif os.path.isdir(f"/proc/{portage.getpid()}/fd"):
    # In order for this function to work in forked subprocesses,
    # os.getpid() must be called from inside the function.
    def get_open_fds():
        return (
            int(fd) for fd in os.listdir(f"/proc/{portage.getpid()}/fd") if fd.isdigit()
        )

else:

    def get_open_fds():
        return range(max_fd_limit)


sandbox_capable = os.path.isfile(SANDBOX_BINARY) and os.access(SANDBOX_BINARY, os.X_OK)

fakeroot_capable = os.path.isfile(FAKEROOT_BINARY) and os.access(
    FAKEROOT_BINARY, os.X_OK
)


def sanitize_fds():
    """
    Set the inheritable flag to False for all open file descriptors,
    except for those corresponding to stdin, stdout, and stderr. This
    ensures that any unintentionally inherited file descriptors will
    not be inherited by child processes.
    """
    if _set_inheritable is not None:
        whitelist = frozenset(
            [
                portage._get_stdin().fileno(),
                sys.__stdout__.fileno(),
                sys.__stderr__.fileno(),
            ]
        )

        for fd in get_open_fds():
            if fd not in whitelist:
                try:
                    _set_inheritable(fd, False)
                except OSError:
                    pass


def spawn_bash(mycommand, debug=False, opt_name=None, **keywords):
    """
    Spawns a bash shell running a specific commands

    @param mycommand: The command for bash to run
    @type mycommand: String
    @param debug: Turn bash debugging on (set -x)
    @type debug: Boolean
    @param opt_name: Name of the spawned process (detaults to binary name)
    @type opt_name: String
    @param keywords: Extra Dictionary arguments to pass to spawn
    @type keywords: Dictionary
    """

    args = [BASH_BINARY]
    if not opt_name:
        opt_name = os.path.basename(mycommand.split()[0])
    if debug:
        # Print commands and their arguments as they are executed.
        args.append("-x")
    args.append("-c")
    args.append(mycommand)
    return spawn(args, opt_name=opt_name, **keywords)


def spawn_sandbox(mycommand, opt_name=None, **keywords):
    if not sandbox_capable:
        return spawn_bash(mycommand, opt_name=opt_name, **keywords)
    args = [SANDBOX_BINARY]
    if not opt_name:
        opt_name = os.path.basename(mycommand.split()[0])
    args.append(mycommand)
    return spawn(args, opt_name=opt_name, **keywords)


def spawn_fakeroot(mycommand, fakeroot_state=None, opt_name=None, **keywords):
    args = [FAKEROOT_BINARY]
    if not opt_name:
        opt_name = os.path.basename(mycommand.split()[0])
    if fakeroot_state:
        open(fakeroot_state, "a").close()
        args.append("-s")
        args.append(fakeroot_state)
        args.append("-i")
        args.append(fakeroot_state)
    args.append("--")
    args.append(BASH_BINARY)
    args.append("-c")
    args.append(mycommand)
    return spawn(args, opt_name=opt_name, **keywords)


_exithandlers = []


def atexit_register(func, *args, **kargs):
    """Wrapper around atexit.register that is needed in order to track
    what is registered.  For example, when portage restarts itself via
    os.execv, the atexit module does not work so we have to do it
    manually by calling the run_exitfuncs() function in this module."""
    # The internal asyncio wrapper module would trigger a circular import
    # if used here.
    if _asyncio.iscoroutinefunction(func):
        # Add this coroutine function to the exit handlers for the loop
        # which is associated with the current thread.
        global_event_loop()._coroutine_exithandlers.append((func, args, kargs))
    else:
        _exithandlers.append((func, args, kargs, portage.getpid()))


def run_exitfuncs():
    """This should behave identically to the routine performed by
    the atexit module at exit time.  It's only necessary to call this
    function when atexit will not work (because of os.execv, for
    example)."""

    # This function is a copy of the private atexit._run_exitfuncs()
    # from the python 2.4.2 sources.  The only difference from the
    # original function is in the output to stderr.
    exc_info = None
    while _exithandlers:
        func, targs, kargs, pid = _exithandlers.pop()
        if pid != portage.getpid():
            # Drop hooks inherited via fork because they can trigger redundant
            # actions as shown in bug 937891. Note that atexit hooks only work
            # after fork since issue 83856 was fixed in Python 3.13.
            continue
        try:
            func(*targs, **kargs)
        except SystemExit:
            exc_info = sys.exc_info()
        except:  # No idea what they called, so we need this broad except here.
            dump_traceback("Error in portage.process.run_exitfuncs", noiselevel=0)
            exc_info = sys.exc_info()

    if exc_info is not None:
        raise exc_info[0](exc_info[1]).with_traceback(exc_info[2])


async def run_coroutine_exitfuncs():
    """
    This is the same as run_exitfuncs but it uses asyncio.iscoroutinefunction
    to check which functions to run. It is called by the AsyncioEventLoop
    _close method just before the loop is closed.

    If the loop is explicitly closed before exit, then that will cause
    run_coroutine_exitfuncs to run before run_exitfuncs. Otherwise, a
    run_exitfuncs hook will close it, causing run_coroutine_exitfuncs to be
    called via run_exitfuncs.
    """
    # The _thread_weakrefs_atexit function makes an adjustment to ensure
    # that global_event_loop() returns the correct loop when it is closing,
    # regardless of which thread the loop was initially associated with.
    _coroutine_exithandlers = global_event_loop()._coroutine_exithandlers
    tasks = []
    while _coroutine_exithandlers:
        func, targs, kargs = _coroutine_exithandlers.pop()
        tasks.append(asyncio.ensure_future(func(*targs, **kargs)))
    tracebacks = []
    exc_info = None
    for task in tasks:
        try:
            await task
        except Exception:
            file = io.StringIO()
            traceback.print_exc(file=file)
            tracebacks.append(file.getvalue())
            exc_info = sys.exc_info()
    if len(tracebacks) > 1:
        for tb in tracebacks[:-1]:
            print(tb, file=sys.stderr, flush=True)
    if exc_info is not None:
        raise exc_info[1].with_traceback(exc_info[2])


def _atexit_register_run_exitfuncs():
    """
    Register the run_exitfuncs atexit hook. If this hook is not called
    before the multiprocessing module's _exit_function, then there will
    be a deadlock. In order to prevent the deadlock, this function must
    be called in order to re-order the hooks after the first process has
    been started via the multiprocessing module. The natural place to
    call this is in the ForkProcess class, though it should also be
    called once before, in case the ForkProcess class is never called.
    """
    atexit.unregister(run_exitfuncs)
    atexit.register(run_exitfuncs)


_atexit_register_run_exitfuncs()

# It used to be necessary for API consumers to remove pids from spawned_pids,
# since otherwise it would accumulate a pids endlessly. Now, spawned_pids is
# just an empty dummy list, so for backward compatibility, ignore ValueError
# for removal on non-existent items.


class _dummy_list(list):
    def remove(self, item):
        # TODO: Trigger a DeprecationWarning here, after stable portage
        # has dummy spawned_pids.
        try:
            list.remove(self, item)
        except ValueError:
            pass


spawned_pids = _dummy_list()


def cleanup():
    pass


@dataclass(frozen=True)
class EnvStats:
    env_size: int
    env_largest_name: str
    env_largest_size: int


def calc_env_stats(env) -> EnvStats:
    @lru_cache(1024)
    def encoded_length(s):
        return len(os.fsencode(s))

    env_size = 0
    env_largest_name = None
    env_largest_size = 0
    for env_name, env_value in env.items():
        env_name_size = encoded_length(env_name)
        env_value_size = encoded_length(env_value)
        # Add two for '=' and the terminating null byte.
        total_size = env_name_size + env_value_size + 2
        if total_size > env_largest_size:
            env_largest_name = env_name
            env_largest_size = total_size
        env_size += total_size

    return EnvStats(env_size, env_largest_name, env_largest_size)


env_too_large_warnings = 0


class AbstractProcess:
    def send_signal(self, sig):
        """Send a signal to the process."""
        if self.returncode is not None:
            # Skip signalling a process that we know has already died.
            return

        try:
            os.kill(self.pid, sig)
        except ProcessLookupError:
            # Suppress the race condition error; bpo-40550.
            pass


class Process(AbstractProcess):
    """
    An object that wraps OS processes which do not have an
    associated multiprocessing.Process instance. Ultimately,
    we need to stop using os.fork() to create these processes
    because it is unsafe for threaded processes as discussed
    in https://github.com/python/cpython/issues/84559.

    Note that if subprocess.Popen is used without pass_fds
    or preexec_fn parameters, then it avoids using os.fork()
    by instead using posix_spawn. This approach is not used
    by spawn because it needs to execute python code prior
    to exec, so it instead uses multiprocessing.Process,
    which only uses os.fork() when the multiprocessing start
    method is fork.
    """

    def __init__(self, pid: int):
        self.pid = pid
        self.returncode = None
        self._exit_waiters = []

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.pid}>"

    async def wait(self):
        """
        Wait for the child process to terminate.

        Set and return the returncode attribute.
        """
        if self.returncode is not None:
            return self.returncode

        loop = global_event_loop()
        if not self._exit_waiters:
            loop._asyncio_child_watcher.add_child_handler(self.pid, self._child_handler)
        waiter = loop.create_future()
        self._exit_waiters.append(waiter)
        return await waiter

    def _child_handler(self, pid, returncode):
        if pid != self.pid:
            raise AssertionError(f"expected pid {self.pid}, got {pid}")
        self.returncode = returncode

        for waiter in self._exit_waiters:
            if not waiter.cancelled():
                waiter.set_result(returncode)
        self._exit_waiters = None

    def terminate(self):
        """Terminate the process with SIGTERM"""
        self.send_signal(signal.SIGTERM)

    def kill(self):
        """Kill the process with SIGKILL"""
        self.send_signal(signal.SIGKILL)


class MultiprocessingProcess(AbstractProcess):
    """
    An object that wraps OS processes created by multiprocessing.Process.
    """

    # Number of seconds between poll attempts for process exit status
    # (after the sentinel has become ready).
    _proc_join_interval = 0.1

    def __init__(self, proc: multiprocessing.Process):
        self._proc = proc
        self.pid = proc.pid
        self.returncode = None
        self._exit_waiters = []

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.pid}>"

    async def wait(self):
        """
        Wait for the child process to terminate.

        Set and return the returncode attribute.
        """
        if self.returncode is not None:
            return self.returncode

        loop = global_event_loop()
        if not self._exit_waiters:
            asyncio.ensure_future(self._proc_join(), loop=loop).add_done_callback(
                self._proc_join_done
            )
        waiter = loop.create_future()
        self._exit_waiters.append(waiter)
        return await waiter

    async def _proc_join(self):
        loop = global_event_loop()
        sentinel_reader = loop.create_future()
        proc = self._proc
        loop.add_reader(
            proc.sentinel,
            lambda: sentinel_reader.done() or sentinel_reader.set_result(None),
        )
        try:
            await sentinel_reader
        finally:
            # If multiprocessing.Process supports the close method, then
            # access to proc.sentinel will raise ValueError if the
            # sentinel has been closed. In this case it's not safe to call
            # remove_reader, since the file descriptor may have been closed
            # and then reallocated to a concurrent coroutine. When the
            # close method is not supported, proc.sentinel remains open
            # until proc's finalizer is called.
            try:
                loop.remove_reader(proc.sentinel)
            except ValueError:
                pass

        # Now that proc.sentinel is ready, poll until process exit
        # status has become available.
        while True:
            proc.join(0)
            if proc.exitcode is not None:
                break
            await asyncio.sleep(self._proc_join_interval, loop=loop)

    def _proc_join_done(self, future):
        # The join task should never be cancelled, so let it raise
        # asyncio.CancelledError here if that somehow happens.
        future.result()

        self.returncode = self._proc.exitcode
        if hasattr(self._proc, "close"):
            self._proc.close()
        self._proc = None

        for waiter in self._exit_waiters:
            if not waiter.cancelled():
                waiter.set_result(self.returncode)
        self._exit_waiters = None

    def terminate(self):
        """Terminate the process with SIGTERM"""
        if self._proc is not None:
            self._proc.terminate()

    def kill(self):
        """Kill the process with SIGKILL"""
        if self._proc is not None:
            self._proc.kill()


def spawn(
    mycommand,
    env=None,
    opt_name=None,
    fd_pipes=None,
    returnpid=False,
    returnproc=False,
    uid=None,
    gid=None,
    groups=None,
    umask=None,
    cwd=None,
    logfile=None,
    path_lookup=True,
    pre_exec=None,
    close_fds=False,
    unshare_net=False,
    unshare_ipc=False,
    unshare_mount=False,
    unshare_pid=False,
    warn_on_large_env=False,
) -> Union[int, MultiprocessingProcess, list[int]]:
    """
    Spawns a given command.

    @param mycommand: the command to execute
    @type mycommand: String or List (Popen style list)
    @param env: If env is not None, it must be a mapping that defines the environment
            variables for the new process; these are used instead of the default behavior
            of inheriting the current process's environment.
    @type env: None or Mapping
    @param opt_name: an optional name for the spawn'd process (defaults to the binary name)
    @type opt_name: String
    @param fd_pipes: A dict of mapping for pipes, { '0': stdin, '1': stdout } for example
            (default is {0:stdin, 1:stdout, 2:stderr})
    @type fd_pipes: Dictionary
    @param returnpid: Return the Process IDs for a successful spawn.
    NOTE: This requires the caller clean up all the PIDs, otherwise spawn will clean them.
    @type returnpid: Boolean
    @param returnproc: Return a MultiprocessingProcess instance (conflicts with logfile parameter).
    NOTE: This requires the caller to asynchronously wait for the MultiprocessingProcess instance.
    @type returnproc: Boolean
    @param uid: User ID to spawn as; useful for dropping privilages
    @type uid: Integer
    @param gid: Group ID to spawn as; useful for dropping privilages
    @type gid: Integer
    @param groups: Group ID's to spawn in: useful for having the process run in multiple group contexts.
    @type groups: List
    @param umask: An integer representing the umask for the process (see man chmod for umask details)
    @type umask: Integer
    @param cwd: Current working directory
    @type cwd: String
    @param logfile: name of a file to use for logging purposes
    @type logfile: String
    @param path_lookup: If the binary is not fully specified then look for it in PATH
    @type path_lookup: Boolean
    @param pre_exec: A function to be called with no arguments just prior to the exec call.
    @type pre_exec: callable
    @param close_fds: If True, then close all file descriptors except those
            referenced by fd_pipes (default is True for python3.3 and earlier, and False for
            python3.4 and later due to non-inheritable file descriptor behavior from PEP 446).
    @type close_fds: Boolean
    @param unshare_net: If True, networking will be unshared from the spawned process
    @type unshare_net: Boolean
    @param unshare_ipc: If True, IPC will be unshared from the spawned process
    @type unshare_ipc: Boolean
    @param unshare_mount: If True, mount namespace will be unshared and mounts will
            be private to the namespace
    @type unshare_mount: Boolean
    @param unshare_pid: If True, PID ns will be unshared from the spawned process
    @type unshare_pid: Boolean

    logfile requires stdout and stderr to be assigned to this process (ie not pointed
       somewhere else.)

    """

    if logfile and returnproc:
        raise ValueError(
            "logfile parameter conflicts with returnproc (use fd_pipes instead)"
        )

    # mycommand is either a str or a list
    if isinstance(mycommand, str):
        mycommand = mycommand.split()

    env = os.environ if env is None else env
    # Sometimes os.environ can fail to pickle as shown in bug 923750
    # comment 4, so copy it to a dict.
    env = env if isinstance(env, dict) else dict(env)

    env_stats = None
    if warn_on_large_env:
        env_stats = calc_env_stats(env)

        global env_too_large_warnings
        if env_stats.env_size > 1024 * 96 and env_too_large_warnings < 3:
            env_too_large_warnings += 1
            writemsg_level(
                f"WARNING: New process environment is large, executing {mycommand} may fail. Size: {env_stats.env_size} bytes. Largest environment variable: {env_stats.env_largest_name} ({env_stats.env_largest_size} bytes)",
                logging.WARNING,
            )

    # If an absolute path to an executable file isn't given
    # search for it unless we've been told not to.
    binary = mycommand[0]
    if binary not in (BASH_BINARY, SANDBOX_BINARY, FAKEROOT_BINARY) and (
        not os.path.isabs(binary)
        or not os.path.isfile(binary)
        or not os.access(binary, os.X_OK)
    ):
        binary = path_lookup and find_binary(binary) or None
        if not binary:
            raise CommandNotFound(mycommand[0])

    # If we haven't been told what file descriptors to use
    # default to propagating our stdin, stdout and stderr.
    if fd_pipes is None:
        fd_pipes = {
            0: portage._get_stdin().fileno(),
            1: sys.__stdout__.fileno(),
            2: sys.__stderr__.fileno(),
        }

    # mypids will hold the pids of all processes created.
    mypids = []

    if logfile:
        # Using a log file requires that stdout and stderr
        # are assigned to the process we're running.
        if 1 not in fd_pipes or 2 not in fd_pipes:
            raise ValueError(fd_pipes)

        # Create a pipe
        (pr, pw) = os.pipe()

        # Create a tee process, giving it our stdout and stderr
        # as well as the read end of the pipe.
        mypids.append(
            spawn(
                ("tee", "-i", "-a", logfile),
                returnproc=True,
                fd_pipes={0: pr, 1: fd_pipes[1], 2: fd_pipes[2]},
            )
        )

        # We don't need the read end of the pipe, so close it.
        os.close(pr)

        # Assign the write end of the pipe to our stdout and stderr.
        fd_pipes[1] = pw
        fd_pipes[2] = pw

    # Cache has_ipv6() result for use in child processes.
    has_ipv6()

    # This caches the libc library lookup and _unshare_validator results
    # in the current process, so that results are cached for use in
    # child processes.
    unshare_flags = 0
    if unshare_net or unshare_ipc or unshare_mount or unshare_pid:
        # from /usr/include/bits/sched.h
        CLONE_NEWNS = 0x00020000
        CLONE_NEWUTS = 0x04000000
        CLONE_NEWIPC = 0x08000000
        CLONE_NEWPID = 0x20000000
        CLONE_NEWNET = 0x40000000

        if unshare_net:
            # UTS namespace to override hostname
            unshare_flags |= CLONE_NEWNET | CLONE_NEWUTS
        if unshare_ipc:
            unshare_flags |= CLONE_NEWIPC
        if unshare_mount:
            # NEWNS = mount namespace
            unshare_flags |= CLONE_NEWNS
        if unshare_pid:
            # we also need mount namespace for slave /proc
            unshare_flags |= CLONE_NEWPID | CLONE_NEWNS

        _unshare_validate(unshare_flags)

    # Force instantiation of portage.data.userpriv_groups before the
    # fork, so that the result is cached in the main process.
    bool(groups)

    start_func = _start_proc if returnproc or not returnpid else _start_fork

    pid = start_func(
        _exec_wrapper,
        args=(
            binary,
            mycommand,
            opt_name,
            fd_pipes,
            env,
            gid,
            groups,
            uid,
            umask,
            cwd,
            pre_exec,
            close_fds,
            unshare_net,
            unshare_ipc,
            unshare_mount,
            unshare_pid,
            unshare_flags,
            env_stats,
        ),
        fd_pipes=fd_pipes,
        close_fds=close_fds,
    )

    if returnproc:
        # _start_proc returns a MultiprocessingProcess instance.
        return pid

    if returnpid and not isinstance(pid, int):
        raise AssertionError(f"fork returned non-integer: {repr(pid)}")

    # Add the pid to our local and the global pid lists.
    mypids.append(pid)

    # If we started a tee process the write side of the pipe is no
    # longer needed, so close it.
    if logfile:
        os.close(pw)

    # If the caller wants to handle cleaning up the processes, we tell
    # it about all processes that were created.
    if returnpid:
        warnings.warn(
            "The portage.process.spawn returnpid parameter is deprecated and replaced by returnproc",
            UserWarning,
            stacklevel=1,
        )
        return mypids

    loop = global_event_loop()

    # Otherwise we clean them up.
    while mypids:
        # Pull the last reader in the pipe chain. If all processes
        # in the pipe are well behaved, it will die when the process
        # it is reading from dies.
        pid = mypids.pop(0)

        # and wait for it.
        retval = loop.run_until_complete(pid.wait())

        if retval:
            # If it failed, kill off anything else that
            # isn't dead yet.
            for pid in mypids:
                waiter = asyncio.ensure_future(pid.wait(), loop)
                try:
                    loop.run_until_complete(
                        asyncio.wait_for(asyncio.shield(waiter), 0.001)
                    )
                except (TimeoutError, asyncio.TimeoutError):
                    pid.terminate()
                    loop.run_until_complete(waiter)

            return retval

    # Everything succeeded
    return 0


__has_ipv6 = None


def has_ipv6():
    """
    Test that both userland and kernel support IPv6, by attempting
    to create a socket and listen on any unused port of the IPv6
    ::1 loopback address.

    @rtype: bool
    @return: True if IPv6 is supported, False otherwise.
    """
    global __has_ipv6

    if __has_ipv6 is None:
        if socket.has_ipv6:
            sock = None
            try:
                # With ipv6.disable=0 and ipv6.disable_ipv6=1, socket creation
                # succeeds, but then the bind call fails with this error:
                # [Errno 99] Cannot assign requested address.
                sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
                sock.bind(("::1", 0))
            except OSError:
                __has_ipv6 = False
            else:
                __has_ipv6 = True
            finally:
                # python2.7 sockets do not support context management protocol
                if sock is not None:
                    sock.close()
        else:
            __has_ipv6 = False

    return __has_ipv6


def _configure_loopback_interface():
    """
    Configure the loopback interface.
    """

    # We add some additional addresses to work around odd behavior in glibc's
    # getaddrinfo() implementation when the AI_ADDRCONFIG flag is set.
    #
    # For example:
    #
    #   struct addrinfo *res, hints = { .ai_family = AF_INET, .ai_flags = AI_ADDRCONFIG };
    #   getaddrinfo("localhost", NULL, &hints, &res);
    #
    # This returns no results if there are no non-loopback addresses
    # configured for a given address family.
    #
    # Bug: https://bugs.gentoo.org/690758
    # Bug: https://sourceware.org/bugzilla/show_bug.cgi?id=12377#c13

    if RtNetlink is None:
        return

    try:
        with RtNetlink() as rtnl:
            ifindex = rtnl.get_link_ifindex(b"lo")
            rtnl.set_link_up(ifindex)
            rtnl.add_address(ifindex, socket.AF_INET, "10.0.0.1", 8)
            if has_ipv6():
                rtnl.add_address(ifindex, socket.AF_INET6, "fd::1", 8)
    except OSError as e:
        writemsg(
            f"Unable to configure loopback interface: {e.strerror}\n", noiselevel=-1
        )


def _exec_wrapper(
    binary,
    mycommand,
    opt_name,
    fd_pipes,
    env,
    gid,
    groups,
    uid,
    umask,
    cwd,
    pre_exec,
    close_fds,
    unshare_net,
    unshare_ipc,
    unshare_mount,
    unshare_pid,
    unshare_flags,
    env_stats,
):
    """
    Calls _exec with the given args and handles any raised Exception.
    The intention is for _exec_wrapper and _exec to be reusable with
    other process cloning implementations besides _start_fork.
    """
    try:
        _exec(
            binary,
            mycommand,
            opt_name,
            fd_pipes,
            env,
            gid,
            groups,
            uid,
            umask,
            cwd,
            pre_exec,
            close_fds,
            unshare_net,
            unshare_ipc,
            unshare_mount,
            unshare_pid,
            unshare_flags,
        )
    except Exception as e:
        if isinstance(e, OSError) and e.errno == errno.E2BIG:
            # If exec() failed with E2BIG, then this is
            # potentially because the environment variables
            # grew to large. The following will gather some
            # stats about the environment and print a
            # diagnostic message to help identifying the
            # culprit. See also
            # - https://bugs.gentoo.org/721088
            # - https://bugs.gentoo.org/830187
            if not env_stats:
                env_stats = calc_env_stats(env)

            writemsg(
                f"ERROR: Executing {mycommand} failed with E2BIG. Child process environment size: {env_stats.env_size} bytes. Largest environment variable: {env_stats.env_largest_name} ({env_stats.env_largest_size} bytes)\n"
            )
        writemsg(f"{e}:\n   {' '.join(mycommand)}\n", noiselevel=-1)
        raise


def _exec(
    binary,
    mycommand,
    opt_name,
    fd_pipes,
    env,
    gid,
    groups,
    uid,
    umask,
    cwd,
    pre_exec,
    close_fds,
    unshare_net,
    unshare_ipc,
    unshare_mount,
    unshare_pid,
    unshare_flags,
):
    """
    Execute a given binary with options

    @param binary: Name of program to execute
    @type binary: String
    @param mycommand: Options for program
    @type mycommand: String
    @param opt_name: Name of process (defaults to binary)
    @type opt_name: String
    @param fd_pipes: Mapping pipes to destination; { 0:0, 1:1, 2:2 }
    @type fd_pipes: Dictionary
    @param env: Key,Value mapping for Environmental Variables
    @type env: Dictionary
    @param gid: Group ID to run the process under
    @type gid: Integer
    @param groups: Groups the Process should be in.
    @type groups: List
    @param uid: User ID to run the process under
    @type uid: Integer
    @param umask: an int representing a unix umask (see man chmod for umask details)
    @type umask: Integer
    @param cwd: Current working directory
    @type cwd: String
    @param pre_exec: A function to be called with no arguments just prior to the exec call.
    @type pre_exec: callable
    @param unshare_net: If True, networking will be unshared from the spawned process
    @type unshare_net: Boolean
    @param unshare_ipc: If True, IPC will be unshared from the spawned process
    @type unshare_ipc: Boolean
    @param unshare_mount: If True, mount namespace will be unshared and mounts will
            be private to the namespace
    @type unshare_mount: Boolean
    @param unshare_pid: If True, PID ns will be unshared from the spawned process
    @type unshare_pid: Boolean
    @param unshare_flags: Flags for the unshare(2) function
    @type unshare_flags: Integer
    @rtype: None
    @return: Never returns (calls os.execve)
    """

    # If the process we're creating hasn't been given a name
    # assign it the name of the executable.
    if not opt_name:
        if binary is portage._python_interpreter:
            # NOTE: PyPy 1.7 will die due to "libary path not found" if argv[0]
            # does not contain the full path of the binary.
            opt_name = binary
        else:
            opt_name = os.path.basename(binary)

    # Set up the command's argument list.
    myargs = [opt_name]
    myargs.extend(mycommand[1:])

    # Avoid a potential UnicodeEncodeError from os.execve().
    myargs = [
        _unicode_encode(x, encoding=_encodings["fs"], errors="strict") for x in myargs
    ]

    # Use default signal handlers in order to avoid problems
    # killing subprocesses as reported in bug #353239.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    # Unregister SIGCHLD handler and wakeup_fd for the parent
    # process's event loop (bug 655656).
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    try:
        wakeup_fd = signal.set_wakeup_fd(-1)
        if wakeup_fd > 0:
            os.close(wakeup_fd)
    except (ValueError, OSError):
        pass

    # Quiet killing of subprocesses by SIGPIPE (see bug #309001).
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    # Avoid issues triggered by inheritance of SIGQUIT handler from
    # the parent process (see bug #289486).
    signal.signal(signal.SIGQUIT, signal.SIG_DFL)

    # Unshare (while still uid==0)
    have_unshare = False
    libc = None
    if unshare_net or unshare_ipc or unshare_mount or unshare_pid:
        (libc, _) = load_libc()
        if libc is not None:
            have_unshare = hasattr(libc, "unshare")

    if not have_unshare:
        # unshare() may not be supported by libc
        unshare_net = False
        unshare_ipc = False
        unshare_mount = False
        unshare_pid = False

    if unshare_net or unshare_ipc or unshare_mount or unshare_pid:
        # Since a failed unshare call could corrupt process
        # state, first validate that the call can succeed.
        # The parent process should call _unshare_validate
        # before it forks, so that all child processes can
        # reuse _unshare_validate results that have been
        # cached by the parent process.
        errno_value = _unshare_validate(unshare_flags)
        if errno_value == 0 and libc.unshare(unshare_flags) != 0:
            errno_value = ctypes.get_errno()
        if errno_value != 0:
            involved_features = []
            if unshare_ipc:
                involved_features.append("ipc-sandbox")
            if unshare_mount:
                involved_features.append("mount-sandbox")
            if unshare_net:
                involved_features.append("network-sandbox")
            if unshare_pid:
                involved_features.append("pid-sandbox")

            writemsg(
                'Unable to unshare: %s (for FEATURES="%s")\n'
                % (
                    errno.errorcode.get(errno_value, "?"),
                    " ".join(involved_features),
                ),
                noiselevel=-1,
            )

            unshare_net = False
            unshare_ipc = False
            unshare_mount = False
            unshare_pid = False

    if unshare_pid:
        # pid namespace requires us to become init
        binary, myargs = (
            portage._python_interpreter,
            [
                portage._python_interpreter,
                os.path.join(portage._bin_path, "pid-ns-init"),
                _unicode_encode("" if uid is None else str(uid)),
                _unicode_encode("" if gid is None else str(gid)),
                _unicode_encode(
                    "" if groups is None else ",".join(str(group) for group in groups)
                ),
                _unicode_encode("" if umask is None else str(umask)),
                _unicode_encode(",".join(str(fd) for fd in fd_pipes)),
                binary,
            ]
            + myargs,
        )
        uid = None
        gid = None
        groups = None
        umask = None

        # Use _start_fork for os.fork() error handling, ensuring
        # that if exec fails then the child process will display
        # a traceback before it exits via os._exit to suppress any
        # finally blocks from parent's call stack (bug 345289).
        main_child_pid = _start_fork(
            _exec2,
            args=(
                binary,
                myargs,
                env,
                gid,
                groups,
                uid,
                umask,
                cwd,
                pre_exec,
                unshare_net,
                unshare_ipc,
                unshare_mount,
                unshare_pid,
                libc,
            ),
            fd_pipes=None,
            close_fds=False,
        )

        # Execute a supervisor process which will forward
        # signals to init and forward exit status to the
        # parent process. The supervisor process runs in
        # the global pid namespace, so skip /proc remount
        # and other setup that's intended only for the
        # init process.
        binary, myargs = portage._python_interpreter, [
            portage._python_interpreter,
            os.path.join(portage._bin_path, "pid-ns-init"),
            str(main_child_pid),
        ]

        os.execve(binary, myargs, env)

    # Reachable only if unshare_pid is False.
    _exec2(
        binary,
        myargs,
        env,
        gid,
        groups,
        uid,
        umask,
        cwd,
        pre_exec,
        unshare_net,
        unshare_ipc,
        unshare_mount,
        unshare_pid,
        libc,
    )


def _exec2(
    binary,
    myargs,
    env,
    gid,
    groups,
    uid,
    umask,
    cwd,
    pre_exec,
    unshare_net,
    unshare_ipc,
    unshare_mount,
    unshare_pid,
    libc,
):
    if unshare_mount:
        # mark the whole filesystem as slave to avoid
        # mounts escaping the namespace
        s = subprocess.Popen(["mount", "--make-rslave", "/"])
        mount_ret = s.wait()
        if mount_ret != 0:
            # TODO: should it be fatal maybe?
            writemsg(
                "Unable to mark mounts slave: %d\n" % (mount_ret,),
                noiselevel=-1,
            )
    if unshare_pid:
        # we need at least /proc being slave
        s = subprocess.Popen(["mount", "--make-slave", "/proc"])
        mount_ret = s.wait()
        if mount_ret != 0:
            # can't proceed with shared /proc
            writemsg(
                "Unable to mark /proc slave: %d\n" % (mount_ret,),
                noiselevel=-1,
            )
            os._exit(1)
        # mount new /proc for our namespace
        s = subprocess.Popen(["mount", "-n", "-t", "proc", "proc", "/proc"])
        mount_ret = s.wait()
        if mount_ret != 0:
            writemsg(
                "Unable to mount new /proc: %d\n" % (mount_ret,),
                noiselevel=-1,
            )
            os._exit(1)
    if unshare_net:
        # use 'localhost' to avoid hostname resolution problems
        try:
            # pypy3 does not implement socket.sethostname()
            new_hostname = b"localhost"
            if hasattr(socket, "sethostname"):
                socket.sethostname(new_hostname)
            else:
                if libc.sethostname(new_hostname, len(new_hostname)) != 0:
                    errno_value = ctypes.get_errno()
                    raise OSError(errno_value, os.strerror(errno_value))
        except Exception as e:
            writemsg(
                f'Unable to set hostname: {e} (for FEATURES="network-sandbox")\n',
                noiselevel=-1,
            )
        _configure_loopback_interface()

    # Set requested process permissions.
    if gid:
        # Cast proxies to int, in case it matters.
        os.setgid(int(gid))
    if groups:
        os.setgroups(groups)
    if uid:
        # Cast proxies to int, in case it matters.
        os.setuid(int(uid))
    if umask:
        os.umask(umask)
    if cwd is not None:
        os.chdir(cwd)
    if pre_exec:
        pre_exec()

    # And switch to the new process.
    os.execve(binary, myargs, env)


class _unshare_validator:
    """
    In order to prevent failed unshare calls from corrupting the state
    of an essential process, validate the relevant unshare call in a
    short-lived subprocess. An unshare call is considered valid if it
    successfully executes in a short-lived subprocess.
    """

    def __init__(self):
        self._results = {}

    def __call__(self, flags):
        """
        Validate unshare with the given flags. Results are cached.

        @rtype: int
        @returns: errno value, or 0 if no error occurred.
        """

        try:
            return self._results[flags]
        except KeyError:
            result = self._results[flags] = self._validate(flags)
            return result

    @classmethod
    def _validate(cls, flags):
        """
        Perform validation.

        @param flags: unshare flags
        @type flags: int
        @rtype: int
        @returns: errno value, or 0 if no error occurred.
        """
        # This ctypes library lookup caches the result for use in the
        # subprocess when the multiprocessing start method is fork.
        (libc, filename) = load_libc()
        if libc is None:
            return errno.ENOTSUP

        parent_pipe, subproc_pipe = multiprocessing.Pipe(duplex=False)

        proc = multiprocessing.Process(
            target=cls._run_subproc,
            args=(subproc_pipe, cls._validate_subproc, (filename, flags)),
        )
        proc.start()
        subproc_pipe.close()

        result = parent_pipe.recv()
        parent_pipe.close()
        proc.join()

        return result

    @staticmethod
    def _run_subproc(subproc_pipe, target, args=(), kwargs={}):
        """
        Call function and send return value to parent process.

        @param subproc_pipe: connection to parent process
        @type subproc_pipe: multiprocessing.Connection
        @param target: target is the callable object to be invoked
        @type target: callable
        @param args: the argument tuple for the target invocation
        @type args: tuple
        @param kwargs: dictionary of keyword arguments for the target invocation
        @type kwargs: dict
        """
        subproc_pipe.send(target(*args, **kwargs))
        subproc_pipe.close()

    @staticmethod
    def _validate_subproc(filename, flags):
        """
        Perform validation. Calls to this method must be isolated in a
        subprocess, since the unshare function is called for purposes of
        validation.

        @param unshare: unshare function
        @type unshare: callable
        @param flags: unshare flags
        @type flags: int
        @rtype: int
        @returns: errno value, or 0 if no error occurred.
        """
        # Since ctypes objects are not picklable for the multiprocessing
        # spawn start method, acquire them here.
        libc = LoadLibrary(filename)
        return 0 if libc.unshare(flags) == 0 else ctypes.get_errno()


_unshare_validate = _unshare_validator()


def _setup_pipes(fd_pipes, close_fds=True, inheritable=None):
    """Setup pipes for a forked process.

    Even when close_fds is False, file descriptors referenced as
    values in fd_pipes are automatically closed if they do not also
    occur as keys in fd_pipes. It is assumed that the caller will
    explicitly add them to the fd_pipes keys if they are intended
    to remain open. This allows for convenient elimination of
    unnecessary duplicate file descriptors.

    WARNING: When not followed by exec, the close_fds behavior
    can trigger interference from destructors that close file
    descriptors. This interference happens when the garbage
    collector intermittently executes such destructors after their
    corresponding file descriptors have been re-used, leading
    to intermittent "[Errno 9] Bad file descriptor" exceptions in
    forked processes. This problem has been observed with PyPy 1.8,
    and also with CPython under some circumstances (as triggered
    by xmpppy in bug #374335). In order to close a safe subset of
    file descriptors, see portage.locks._close_fds().

    NOTE: When not followed by exec, even when close_fds is False,
    it's still possible for dup2() calls to cause interference in a
    way that's similar to the way that close_fds interferes (since
    dup2() has to close the target fd if it happens to be open).
    It's possible to avoid such interference by using allocated
    file descriptors as the keys in fd_pipes. For example:

            pr, pw = os.pipe()
            fd_pipes[pw] = pw

    By using the allocated pw file descriptor as the key in fd_pipes,
    it's not necessary for dup2() to close a file descriptor (it
    actually does nothing in this case), which avoids possible
    interference.
    """
    fd_pipes = {} if fd_pipes is None else fd_pipes
    reverse_map = {}
    # To protect from cases where direct assignment could
    # clobber needed fds ({1:2, 2:1}) we create a reverse map
    # in order to know when it's necessary to create temporary
    # backup copies with os.dup().
    for newfd, oldfd in fd_pipes.items():
        newfds = reverse_map.get(oldfd)
        if newfds is None:
            newfds = []
            reverse_map[oldfd] = newfds
        newfds.append(newfd)

    # Assign newfds via dup2(), making temporary backups when
    # necessary, and closing oldfd if the caller has not
    # explicitly requested for it to remain open by adding
    # it to the keys of fd_pipes.
    while reverse_map:
        oldfd, newfds = reverse_map.popitem()
        old_fdflags = None

        for newfd in newfds:
            if newfd in reverse_map:
                # Make a temporary backup before re-assignment, assuming
                # that backup_fd won't collide with a key in reverse_map
                # (since all of the keys correspond to open file
                # descriptors, and os.dup() only allocates a previously
                # unused file discriptors).
                backup_fd = os.dup(newfd)
                reverse_map[backup_fd] = reverse_map.pop(newfd)

            if oldfd != newfd:
                os.dup2(oldfd, newfd)
                if _set_inheritable is not None:
                    # Don't do this unless _set_inheritable is available,
                    # since it's used below to ensure correct state, and
                    # otherwise /dev/null stdin fails to inherit (at least
                    # with Python versions from 3.1 to 3.3).
                    if old_fdflags is None:
                        old_fdflags = fcntl.fcntl(oldfd, fcntl.F_GETFD)
                    fcntl.fcntl(newfd, fcntl.F_SETFD, old_fdflags)

            if _set_inheritable is not None:
                inheritable_state = None
                if not (old_fdflags is None or _FD_CLOEXEC is None):
                    inheritable_state = not bool(old_fdflags & _FD_CLOEXEC)

                if inheritable is not None:
                    if inheritable_state is not inheritable:
                        _set_inheritable(newfd, inheritable)

                elif newfd in (0, 1, 2):
                    if inheritable_state is not True:
                        _set_inheritable(newfd, True)

        if oldfd not in fd_pipes:
            # If oldfd is not a key in fd_pipes, then it's safe
            # to close now, since we've already made all of the
            # requested duplicates. This also closes every
            # backup_fd that may have been created on previous
            # iterations of this loop.
            os.close(oldfd)

    if close_fds:
        # Then close _all_ fds that haven't been explicitly
        # requested to be kept open.
        for fd in get_open_fds():
            if fd not in fd_pipes:
                try:
                    os.close(fd)
                except OSError:
                    pass


def _start_fork(
    target: Callable[..., None],
    args: Optional[tuple[Any, ...]] = (),
    kwargs: Optional[dict[str, Any]] = {},
    fd_pipes: Optional[dict[int, int]] = None,
    close_fds: Optional[bool] = True,
) -> int:
    """
    Execute the target function in a fork. The fd_pipes and
    close_fds parameters are handled in the fork, before the target
    function is called. The args and kwargs parameters are passed
    as positional and keyword arguments for the target function.

    The target, args, and kwargs parameters are intended to
    be equivalent to the corresponding multiprocessing.Process
    constructor parameters.

    Ultimately, the intention is for spawn to support other
    process cloning implementations besides _start_fork, since
    fork is unsafe for threaded processes as discussed in
    https://github.com/python/cpython/issues/84559.
    """
    parent_pid = portage.getpid()
    pid = None
    try:
        pid = os.fork()

        if pid == 0:
            try:
                _setup_pipes(fd_pipes, close_fds=close_fds, inheritable=True)
                target(*args, **kwargs)
            except Exception:
                # We need to catch _any_ exception and display it since the child
                # process must unconditionally exit via os._exit() if exec fails.
                traceback.print_exc()
                sys.stderr.flush()
    finally:
        # Don't used portage.getpid() here, in case there is a race
        # with getpid cache invalidation via _ForkWatcher hook.
        if pid == 0 or (pid is None and _os.getpid() != parent_pid):
            # Call os._exit() from a finally block in order
            # to suppress any finally blocks from earlier
            # in the call stack (see bug #345289). This
            # finally block has to be setup before the fork
            # in order to avoid a race condition.
            os._exit(1)
    return pid


class _chain_pre_exec_fns:
    """
    Wraps a target function to call pre_exec functions just before
    the original target function.
    """

    def __init__(self, target, *args):
        self._target = target
        self._pre_exec_fns = args

    def __call__(self, *args, **kwargs):
        for pre_exec in self._pre_exec_fns:
            pre_exec()
        return self._target(*args, **kwargs)


def _setup_pipes_after_fork(fd_pipes):
    for fd in set(fd_pipes.values()):
        os.set_inheritable(fd, True)
    _setup_pipes(fd_pipes, close_fds=False, inheritable=True)


def _start_proc(
    target: Callable[..., None],
    args: Optional[tuple[Any, ...]] = (),
    kwargs: Optional[dict[str, Any]] = {},
    fd_pipes: Optional[dict[int, int]] = None,
    close_fds: Optional[bool] = False,
) -> MultiprocessingProcess:
    """
    Execute the target function using multiprocess.Process.
    If the close_fds parameter is True then NotImplementedError
    is raised, since it is risky to forcefully close file
    descriptors that have references (bug 374335), and PEP 446
    should ensure that any relevant file descriptors are
    non-inheritable and therefore automatically closed on exec.
    """
    if close_fds:
        raise NotImplementedError(
            "close_fds is not supported (since file descriptors are non-inheritable by default for exec)"
        )

    # Manage fd_pipes inheritance for spawn/exec (bug 923755),
    # which ForkProcess does not handle because its target
    # function does not necessarily exec.
    if fd_pipes and multiprocessing.get_start_method() == "fork":
        target = _chain_pre_exec_fns(target, partial(_setup_pipes_after_fork, fd_pipes))
        fd_pipes = None

    proc = ForkProcess(
        scheduler=global_event_loop(),
        target=target,
        args=args,
        kwargs=kwargs,
        fd_pipes=fd_pipes,
        create_pipe=False,  # Pipe creation is delegated to the caller (see bug 923750).
    )
    proc.start()

    # ForkProcess conveniently holds a MultiprocessingProcess
    # instance that is suitable to return here, but use _GCProtector
    # to protect the ForkProcess instance from being garbage collected
    # and triggering messages like this (bug 925456):
    # [ERROR] Task was destroyed but it is pending!
    return _GCProtector(proc._proc, proc.async_wait)


class _GCProtector(ObjectProxy):
    """
    Proxy a target object, and also hold a reference to something
    extra in order to protect it from garbage collection. Override
    the wait method to first call target's wait method and then
    wait for extra (a coroutine function) before returning the result.
    """

    __slots__ = ("_extra", "_target")

    def __init__(self, target, extra):
        super().__init__()
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_extra", extra)

    def _get_target(self):
        return object.__getattribute__(self, "_target")

    def __getattribute__(self, attr):
        if attr == "wait":
            return object.__getattribute__(self, attr)
        return getattr(object.__getattribute__(self, "_target"), attr)

    async def wait(self):
        """
        Wrap the target's wait method to also wait for an extra
        coroutine function.
        """
        result = await object.__getattribute__(self, "_target").wait()
        await object.__getattribute__(self, "_extra")()
        return result


def find_binary(binary):
    """
    Given a binary name, find the binary in PATH

    @param binary: Name of the binary to find
    @type string
    @rtype: None or string
    @return: full path to binary or None if the binary could not be located.
    """
    paths = os.environ.get("PATH", "")
    if isinstance(binary, bytes):
        # return bytes when input is bytes
        paths = paths.encode(sys.getfilesystemencoding(), "surrogateescape")
        paths = paths.split(b":")
    else:
        paths = paths.split(":")

    for path in paths:
        filename = _os.path.join(path, binary)
        if _os.access(filename, os.X_OK) and _os.path.isfile(filename):
            return filename
    return None
