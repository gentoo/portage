# Copyright 2020-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools
import subprocess

from _emerge.AsynchronousTask import AsynchronousTask

from portage import os
from portage.util import shlex_split
from portage.util._async.PipeLogger import PipeLogger
from portage.util._async.PopenProcess import PopenProcess
from portage.util.futures import asyncio

class BuildLogger(AsynchronousTask):
	"""
	Write to a log file, with compression support provided by PipeLogger.
	If the log_filter_file parameter is specified, then it is interpreted
	as a command to execute which filters log output (see the
	PORTAGE_LOG_FILTER_FILE_CMD variable in make.conf(5)). The stdin property
	provides access to a writable binary file stream (refers to a pipe)
	that log content should be written to (usually redirected from
	subprocess stdout and stderr streams).
	"""

	__slots__ = ('env', 'log_path', 'log_filter_file', '_main_task', '_main_task_cancel', '_stdin')

	@property
	def stdin(self):
		return self._stdin

	def _start(self):
		filter_proc = None
		log_input = None
		if self.log_path is not None:
			log_filter_file = self.log_filter_file
			if log_filter_file is not None:
				split_value = shlex_split(log_filter_file)
				log_filter_file = split_value if split_value else None
			if log_filter_file:
				filter_input, stdin = os.pipe()
				log_input, filter_output = os.pipe()
				try:
					filter_proc = PopenProcess(
						proc=subprocess.Popen(
							log_filter_file,
							env=self.env,
							stdin=filter_input,
							stdout=filter_output,
							stderr=filter_output,
						),
						scheduler=self.scheduler,
					)
					filter_proc.start()
				except EnvironmentError:
					# Maybe the command is missing or broken somehow...
					os.close(filter_input)
					os.close(stdin)
					os.close(log_input)
					os.close(filter_output)
				else:
					self._stdin = os.fdopen(stdin, 'wb', 0)
					os.close(filter_input)
					os.close(filter_output)

		if self._stdin is None:
			# Since log_filter_file is unspecified or refers to a file
			# that is missing or broken somehow, create a pipe that
			# logs directly to pipe_logger.
			log_input, stdin = os.pipe()
			self._stdin = os.fdopen(stdin, 'wb', 0)

		# Set background=True so that pipe_logger does not log to stdout.
		pipe_logger = PipeLogger(background=True,
			scheduler=self.scheduler, input_fd=log_input,
			log_file_path=self.log_path)
		pipe_logger.start()

		self._main_task_cancel = functools.partial(self._main_cancel, filter_proc, pipe_logger)
		self._main_task = asyncio.ensure_future(self._main(filter_proc, pipe_logger), loop=self.scheduler)
		self._main_task.add_done_callback(self._main_exit)

	async def _main(self, filter_proc, pipe_logger):
		try:
			if pipe_logger.poll() is None:
				await pipe_logger.async_wait()
			if filter_proc is not None and filter_proc.poll() is None:
				await filter_proc.async_wait()
		except asyncio.CancelledError:
			self._main_cancel(filter_proc, pipe_logger)
			raise

	def _main_cancel(self, filter_proc, pipe_logger):
		if pipe_logger.poll() is None:
			pipe_logger.cancel()
		if filter_proc is not None and filter_proc.poll() is None:
			filter_proc.cancel()

	def _cancel(self):
		if self._main_task is not None:
			if not self._main_task.done():
				if self._main_task_cancel is not None:
					self._main_task_cancel()
					self._main_task_cancel = None
				self._main_task.cancel()
		if self._stdin is not None and not self._stdin.closed:
			self._stdin.close()

	def _main_exit(self, main_task):
		self._main_task = None
		self._main_task_cancel = None
		try:
			main_task.result()
		except asyncio.CancelledError:
			self.cancel()
			self._was_cancelled()
		self.returncode = self.returncode or 0
		self._async_wait()
