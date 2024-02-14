# Copyright 2015-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools
import pickle
import traceback

from portage import multiprocessing, os
from portage.util._async.ForkProcess import ForkProcess
from _emerge.PipeReader import PipeReader


class AsyncFunction(ForkProcess):
    """
    Execute a function call in a fork, and retrieve the function
    return value via pickling/unpickling, accessible as the
    "result" attribute after the forked process has exited.
    """

    __slots__ = (
        "result",
        "_async_func_reader",
    )

    def _start(self):
        pr, pw = multiprocessing.Pipe(duplex=False)
        self._async_func_reader = PipeReader(
            input_files={"input": pr}, scheduler=self.scheduler
        )
        self._async_func_reader.addExitListener(self._async_func_reader_exit)
        self._async_func_reader.start()
        # args and kwargs are passed as additional args by ForkProcess._bootstrap.
        self.target = functools.partial(self._target_wrapper, pw, self.target)
        ForkProcess._start(self)
        pw.close()

    @staticmethod
    def _target_wrapper(pw, target, *args, **kwargs):
        try:
            result = target(*args, **kwargs)
            result_bytes = pickle.dumps(result)
            while result_bytes:
                result_bytes = result_bytes[os.write(pw.fileno(), result_bytes) :]
        except Exception:
            traceback.print_exc()
            return 1

        return os.EX_OK

    def _async_waitpid(self):
        # Ignore this event, since we want to ensure that we exit
        # only after _async_func_reader_exit has reached EOF.
        if self._async_func_reader is None:
            ForkProcess._async_waitpid(self)

    def _async_wait(self):
        if self._async_func_reader is None:
            ForkProcess._async_wait(self)

    def _async_func_reader_exit(self, pipe_reader):
        try:
            self.result = pickle.loads(pipe_reader.getvalue())
        except Exception:
            # The child process will have printed a traceback in this case,
            # and returned an unsuccessful returncode.
            pass
        self._async_func_reader = None
        if self.returncode is None:
            self._async_waitpid()
        else:
            self._unregister()
            self._async_wait()

    def _unregister(self):
        ForkProcess._unregister(self)

        pipe_reader = self._async_func_reader
        if pipe_reader is not None:
            self._async_func_reader = None
            pipe_reader.removeExitListener(self._async_func_reader_exit)
            pipe_reader.cancel()
