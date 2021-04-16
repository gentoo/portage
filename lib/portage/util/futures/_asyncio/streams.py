# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import os

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'_emerge.PipeReader:PipeReader',
	'portage.util.futures:asyncio',
)


def _reader(input_file, loop=None):
	"""
	Asynchronously read a binary input file, and close it when
	it reaches EOF.

	@param input_file: binary input file descriptor
	@type input_file: file or int
	@param loop: asyncio.AbstractEventLoop (or compatible)
	@type loop: event loop
	@return: bytes
	@rtype: asyncio.Future (or compatible)
	"""
	loop = asyncio._wrap_loop(loop)
	future = loop.create_future()
	_Reader(future, input_file, loop)
	return future


class _Reader:
	def __init__(self, future, input_file, loop):
		self._future = future
		self._pipe_reader = PipeReader(
			input_files={'input_file':input_file}, scheduler=loop)

		self._future.add_done_callback(self._cancel_callback)
		self._pipe_reader.addExitListener(self._eof)
		self._pipe_reader.start()

	def _cancel_callback(self, future):
		if future.cancelled():
			self._cancel()

	def _eof(self, pipe_reader):
		self._pipe_reader = None
		self._future.set_result(pipe_reader.getvalue())

	def _cancel(self):
		if self._pipe_reader is not None and self._pipe_reader.poll() is None:
			self._pipe_reader.removeExitListener(self._eof)
			self._pipe_reader.cancel()
			self._pipe_reader = None


async def _writer(output_file, content, loop=DeprecationWarning):
	"""
	Asynchronously write bytes to output file. The output file is
	assumed to be in non-blocking mode. If an EnvironmentError
	other than EAGAIN is encountered, which typically indicates that
	the other end of the pipe has closed, the error is raised.
	This function is a coroutine.

	@param output_file: output file
	@type output_file: file object
	@param content: content to write
	@type content: bytes
	@param loop: deprecated
	"""
	loop = asyncio.get_event_loop()
	fd = output_file.fileno()
	while content:
		try:
			content = content[os.write(fd, content):]
		except EnvironmentError as e:
			if e.errno != errno.EAGAIN:
				raise
			waiter = loop.create_future()
			loop.add_writer(fd, lambda: waiter.done() or waiter.set_result(None))
			try:
				await waiter
			finally:
				# The loop and output file may have been closed.
				if not loop.is_closed():
					waiter.done() or waiter.cancel()
					# Do not call remove_writer in cases where fd has
					# been closed and then re-allocated to a concurrent
					# coroutine as in bug 716636.
					if not output_file.closed:
						loop.remove_writer(fd)
