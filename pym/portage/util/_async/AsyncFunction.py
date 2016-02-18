# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import pickle
import traceback

from portage import os
from portage.util._async.ForkProcess import ForkProcess
from _emerge.PipeReader import PipeReader

class AsyncFunction(ForkProcess):
	"""
	Execute a function call in a fork, and retrieve the function
	return value via pickling/unpickling, accessible as the
	"result" attribute after the forked process has exited.
	"""

	# NOTE: This class overrides the meaning of the SpawnProcess 'args'
	# attribute, and uses it to hold the positional arguments for the
	# 'target' function.
	__slots__ = ('kwargs', 'result', 'target',
		'_async_func_reader', '_async_func_reader_pw')

	def _start(self):
		pr, pw = os.pipe()
		self.fd_pipes = {}
		self.fd_pipes[pw] = pw
		self._async_func_reader_pw = pw
		self._async_func_reader = PipeReader(
			input_files={"input":pr},
			scheduler=self.scheduler)
		self._async_func_reader.addExitListener(self._async_func_reader_exit)
		self._async_func_reader.start()
		ForkProcess._start(self)
		os.close(pw)

	def _run(self):
		try:
			result = self.target(*(self.args or []), **(self.kwargs or {}))
			os.write(self._async_func_reader_pw, pickle.dumps(result))
		except Exception:
			traceback.print_exc()
			return 1

		return os.EX_OK

	def _pipe_logger_exit(self, pipe_logger):
		# Ignore this event, since we want to ensure that we exit
		# only after _async_func_reader_exit has reached EOF.
		self._pipe_logger = None

	def _async_func_reader_exit(self, pipe_reader):
		try:
			self.result = pickle.loads(pipe_reader.getvalue())
		except Exception:
			# The child process will have printed a traceback in this case,
			# and returned an unsuccessful returncode.
			pass
		self._async_func_reader = None
		self._unregister()
		self.wait()

	def _unregister(self):
		ForkProcess._unregister(self)

		pipe_reader = self._async_func_reader
		if pipe_reader is not None:
			self._async_func_reader = None
			pipe_reader.removeExitListener(self._async_func_reader_exit)
			pipe_reader.cancel()
