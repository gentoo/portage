# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import os

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'_emerge.PipeReader:PipeReader',
	'portage.util.futures:asyncio',
	'portage.util.futures.unix_events:_set_nonblocking',
)
from portage.util.futures.compat_coroutine import coroutine


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


class _Reader(object):
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


@coroutine
def _writer(output_file, content, loop=None):
	"""
	Asynchronously write bytes to output file, and close it when
	done. If an EnvironmentError other than EAGAIN is encountered,
	which typically indicates that the other end of the pipe has
	close, the error is raised. This function is a coroutine.

	@param output_file: output file descriptor
	@type output_file: file or int
	@param content: content to write
	@type content: bytes
	@param loop: asyncio.AbstractEventLoop (or compatible)
	@type loop: event loop
	"""
	fd = output_file if isinstance(output_file, int) else output_file.fileno()
	_set_nonblocking(fd)
	loop = asyncio._wrap_loop(loop)
	try:
		while content:
			waiter = loop.create_future()
			loop.add_writer(fd, lambda: waiter.set_result(None))
			try:
				yield waiter
				while content:
					try:
						content = content[os.write(fd, content):]
					except EnvironmentError as e:
						if e.errno == errno.EAGAIN:
							break
						else:
							raise
			finally:
				loop.remove_writer(fd)
	except GeneratorExit:
		raise
	finally:
		os.close(output_file) if isinstance(output_file, int) else output_file.close()
