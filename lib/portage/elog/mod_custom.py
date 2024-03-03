# elog/mod_custom.py - elog dispatch module
# Copyright 2006-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import types

import portage
import portage.elog.mod_save
import portage.exception
import portage.process
from portage.util.futures import asyncio

# Since elog_process is typically called while the event loop is
# running, hold references to spawned processes and wait for them
# asynchronously, ultimately waiting for them if necessary when
# the AsyncioEventLoop _close_main method calls _async_finalize
# via portage.process.run_coroutine_exitfuncs().
_proc_refs = None


def _get_procs() -> list[tuple[portage.process.MultiprocessingProcess, asyncio.Future]]:
    """
    Return list of (proc, asyncio.ensure_future(proc.wait())) which is not
    inherited from the parent after fork.
    """
    global _proc_refs
    if _proc_refs is None or _proc_refs.pid != portage.getpid():
        _proc_refs = types.SimpleNamespace(pid=portage.getpid(), procs=[])
        portage.process.atexit_register(_async_finalize)
    return _proc_refs.procs


def process(mysettings, key, logentries, fulltext):
    elogfilename = portage.elog.mod_save.process(mysettings, key, logentries, fulltext)

    if not mysettings.get("PORTAGE_ELOG_COMMAND"):
        raise portage.exception.MissingParameter(
            "!!! Custom logging requested but PORTAGE_ELOG_COMMAND is not defined"
        )
    else:
        mylogcmd = mysettings["PORTAGE_ELOG_COMMAND"]
        mylogcmd = mylogcmd.replace("${LOGFILE}", elogfilename)
        mylogcmd = mylogcmd.replace("${PACKAGE}", key)
        loop = asyncio.get_event_loop()
        proc = portage.process.spawn_bash(mylogcmd, returnproc=True)
        procs = _get_procs()
        procs.append((proc, asyncio.ensure_future(proc.wait(), loop=loop)))
        for index, (proc, waiter) in reversed(list(enumerate(procs))):
            if not waiter.done():
                continue
            del procs[index]
            if waiter.result() != 0:
                raise portage.exception.PortageException(
                    f"!!! PORTAGE_ELOG_COMMAND failed with exitcode {waiter.result()}"
                )


async def _async_finalize():
    """
    Async finalize is preferred, since we can wait for process exit status.
    """
    procs = _get_procs()
    while procs:
        proc, waiter = procs.pop()
        if (await waiter) != 0:
            raise portage.exception.PortageException(
                f"!!! PORTAGE_ELOG_COMMAND failed with exitcode {waiter.result()}"
            )


def finalize():
    """
    NOTE: This raises PortageException if there are any processes
    still running, so it's better to use _async_finalize instead
    (invoked via portage.process.run_coroutine_exitfuncs() in
    the AsyncioEventLoop _close_main method).
    """
    procs = _get_procs()
    while procs:
        proc, waiter = procs.pop()
        if not waiter.done():
            waiter.cancel()
            proc.terminate()
            raise portage.exception.PortageException(
                f"!!! PORTAGE_ELOG_COMMAND was killed after it was found running in the background (pid {proc.pid})"
            )
        elif waiter.result() != 0:
            raise portage.exception.PortageException(
                f"!!! PORTAGE_ELOG_COMMAND failed with exitcode {waiter.result()}"
            )
