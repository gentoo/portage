# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'AbstractChildWatcher',
	'DefaultEventLoopPolicy',
)

try:
	from asyncio.base_subprocess import BaseSubprocessTransport as _BaseSubprocessTransport
	from asyncio.unix_events import AbstractChildWatcher as _AbstractChildWatcher
	from asyncio.transports import ReadTransport as _ReadTransport
except ImportError:
	_AbstractChildWatcher = object
	_BaseSubprocessTransport = object
	_ReadTransport = object

import errno
import fcntl
import functools
import logging
import os
import stat
import subprocess

from portage.util._eventloop.global_event_loop import (
	global_event_loop as _global_event_loop,
)
from portage.util.futures import (
	asyncio,
	events,
)
from portage.util.futures.futures import Future


class _PortageEventLoop(events.AbstractEventLoop):
	"""
	Implementation of asyncio.AbstractEventLoop which wraps portage's
	internal event loop.
	"""

	def __init__(self, loop):
		"""
		@type loop: EventLoop
		@param loop: an instance of portage's internal event loop
		"""
		self._loop = loop
		self.call_soon = loop.call_soon
		self.call_soon_threadsafe = loop.call_soon_threadsafe
		self.call_later = loop.call_later
		self.call_at = loop.call_at
		self.is_running = loop.is_running
		self.is_closed = loop.is_closed
		self.close = loop.close
		self.create_future = loop.create_future
		self.add_reader = loop.add_reader
		self.remove_reader = loop.remove_reader
		self.add_writer = loop.add_writer
		self.remove_writer = loop.remove_writer
		self.run_in_executor = loop.run_in_executor
		self.time = loop.time
		self.default_exception_handler = loop.default_exception_handler
		self.call_exception_handler = loop.call_exception_handler
		self.set_debug = loop.set_debug
		self.get_debug = loop.get_debug

	def run_until_complete(self, future):
		"""
		Run the event loop until a Future is done.

		@type future: asyncio.Future
		@param future: a Future to wait for
		@rtype: object
		@return: the Future's result
		@raise: the Future's exception
		"""
		return self._loop.run_until_complete(
			asyncio.ensure_future(future, loop=self))

	def create_task(self, coro):
		"""
		Schedule a coroutine object.

		@type coro: coroutine
		@param coro: a coroutine to schedule
		@rtype: asyncio.Task
		@return: a task object
		"""
		return asyncio.Task(coro, loop=self)

	def connect_read_pipe(self, protocol_factory, pipe):
		"""
		Register read pipe in event loop. Set the pipe to non-blocking mode.

		@type protocol_factory: callable
		@param protocol_factory: must instantiate object with Protocol interface
		@type pipe: file
		@param pipe: a pipe to read from
		@rtype: asyncio.Future
		@return: Return pair (transport, protocol), where transport supports the
			ReadTransport interface.
		"""
		protocol = protocol_factory()
		result = self.create_future()
		waiter = self.create_future()
		transport = self._make_read_pipe_transport(pipe, protocol, waiter=waiter)

		def waiter_callback(waiter):
			try:
				waiter.result()
			except Exception as e:
				transport.close()
				result.set_exception(e)
			else:
				result.set_result((transport, protocol))

		waiter.add_done_callback(waiter_callback)
		return result

	def subprocess_exec(self, protocol_factory, program, *args, **kwargs):
		"""
		Run subprocesses asynchronously using the subprocess module.

		@type protocol_factory: callable
		@param protocol_factory: must instantiate a subclass of the
			asyncio.SubprocessProtocol class
		@type program: str or bytes
		@param program: the program to execute
		@type args: str or bytes
		@param args: program's arguments
		@type kwargs: varies
		@param kwargs: subprocess.Popen parameters
		@rtype: asyncio.Future
		@return: Returns a pair of (transport, protocol), where transport
			is an instance of BaseSubprocessTransport
		"""

		# python2.7 does not allow arguments with defaults after *args
		stdin = kwargs.pop('stdin', subprocess.PIPE)
		stdout = kwargs.pop('stdout', subprocess.PIPE)
		stderr = kwargs.pop('stderr', subprocess.PIPE)

		if stdin == subprocess.PIPE:
			# Requires connect_write_pipe implementation, for example
			# see asyncio.unix_events._UnixWritePipeTransport.
			raise NotImplementedError()

		universal_newlines = kwargs.pop('universal_newlines', False)
		shell = kwargs.pop('shell', False)
		bufsize = kwargs.pop('bufsize', 0)

		if universal_newlines:
			raise ValueError("universal_newlines must be False")
		if shell:
			raise ValueError("shell must be False")
		if bufsize != 0:
			raise ValueError("bufsize must be 0")
		popen_args = (program,) + args
		for arg in popen_args:
			if not isinstance(arg, (str, bytes)):
				raise TypeError("program arguments must be "
								"a bytes or text string, not %s"
								% type(arg).__name__)
		result = self.create_future()
		self._make_subprocess_transport(
			result, protocol_factory(), popen_args, False, stdin, stdout, stderr,
			bufsize, **kwargs)
		return result

	def _make_read_pipe_transport(self, pipe, protocol, waiter=None,
								  extra=None):
		return _UnixReadPipeTransport(self, pipe, protocol, waiter, extra)

	def _make_subprocess_transport(self, result, protocol, args, shell,
		stdin, stdout, stderr, bufsize, extra=None, **kwargs):
		waiter = self.create_future()
		transp = _UnixSubprocessTransport(self,
			protocol, args, shell, stdin, stdout, stderr, bufsize,
			waiter=waiter, extra=extra,
			**kwargs)

		self._loop._asyncio_child_watcher.add_child_handler(
			transp.get_pid(), self._child_watcher_callback, transp)

		waiter.add_done_callback(functools.partial(
			self._subprocess_transport_callback, transp, protocol, result))

	def _subprocess_transport_callback(self, transp, protocol, result, waiter):
		if waiter.exception() is None:
			result.set_result((transp, protocol))
		else:
			transp.close()
			wait_transp = asyncio.ensure_future(transp._wait(), loop=self)
			wait_transp.add_done_callback(
				functools.partial(self._subprocess_transport_failure,
				result, waiter.exception()))

	def _child_watcher_callback(self, pid, returncode, transp):
		self.call_soon_threadsafe(transp._process_exited, returncode)

	def _subprocess_transport_failure(self, result, exception, wait_transp):
		result.set_exception(wait_transp.exception() or exception)


if hasattr(os, 'set_blocking'):
	def _set_nonblocking(fd):
		os.set_blocking(fd, False)
else:
	def _set_nonblocking(fd):
		flags = fcntl.fcntl(fd, fcntl.F_GETFL)
		flags = flags | os.O_NONBLOCK
		fcntl.fcntl(fd, fcntl.F_SETFL, flags)


class _UnixReadPipeTransport(_ReadTransport):
	"""
	This is identical to the standard library's private
	asyncio.unix_events._UnixReadPipeTransport class, except that it
	only calls public AbstractEventLoop methods.
	"""

	max_size = 256 * 1024  # max bytes we read in one event loop iteration

	def __init__(self, loop, pipe, protocol, waiter=None, extra=None):
		super().__init__(extra)
		self._extra['pipe'] = pipe
		self._loop = loop
		self._pipe = pipe
		self._fileno = pipe.fileno()
		self._protocol = protocol
		self._closing = False

		mode = os.fstat(self._fileno).st_mode
		if not (stat.S_ISFIFO(mode) or
				stat.S_ISSOCK(mode) or
				stat.S_ISCHR(mode)):
			self._pipe = None
			self._fileno = None
			self._protocol = None
			raise ValueError("Pipe transport is for pipes/sockets only.")

		_set_nonblocking(self._fileno)

		self._loop.call_soon(self._protocol.connection_made, self)
		# only start reading when connection_made() has been called
		self._loop.call_soon(self._loop.add_reader,
							 self._fileno, self._read_ready)
		if waiter is not None:
			# only wake up the waiter when connection_made() has been called
			self._loop.call_soon(
				lambda: None if waiter.cancelled() else waiter.set_result(None))

	def _read_ready(self):
		try:
			data = os.read(self._fileno, self.max_size)
		except (BlockingIOError, InterruptedError):
			pass
		except OSError as exc:
			self._fatal_error(exc, 'Fatal read error on pipe transport')
		else:
			if data:
				self._protocol.data_received(data)
			else:
				self._closing = True
				self._loop.remove_reader(self._fileno)
				self._loop.call_soon(self._protocol.eof_received)
				self._loop.call_soon(self._call_connection_lost, None)

	def pause_reading(self):
		self._loop.remove_reader(self._fileno)

	def resume_reading(self):
		self._loop.add_reader(self._fileno, self._read_ready)

	def set_protocol(self, protocol):
		self._protocol = protocol

	def get_protocol(self):
		return self._protocol

	def is_closing(self):
		return self._closing

	def close(self):
		if not self._closing:
			self._close(None)

	def _fatal_error(self, exc, message='Fatal error on pipe transport'):
		# should be called by exception handler only
		if (isinstance(exc, OSError) and exc.errno == errno.EIO):
			if self._loop.get_debug():
				logging.debug("%r: %s", self, message, exc_info=True)
		else:
			self._loop.call_exception_handler({
				'message': message,
				'exception': exc,
				'transport': self,
				'protocol': self._protocol,
			})
		self._close(exc)

	def _close(self, exc):
		self._closing = True
		self._loop.remove_reader(self._fileno)
		self._loop.call_soon(self._call_connection_lost, exc)

	def _call_connection_lost(self, exc):
		try:
			self._protocol.connection_lost(exc)
		finally:
			self._pipe.close()
			self._pipe = None
			self._protocol = None
			self._loop = None


class _UnixSubprocessTransport(_BaseSubprocessTransport):
	"""
	This is identical to the standard library's private
	asyncio.unix_events._UnixSubprocessTransport class, except that
	subprocess.PIPE is not implemented for stdin, since that would
	require connect_write_pipe support in the event loop. For example,
	see the asyncio.unix_events._UnixWritePipeTransport class.
	"""
	def _start(self, args, shell, stdin, stdout, stderr, bufsize, **kwargs):
		self._proc = subprocess.Popen(
			args, shell=shell, stdin=stdin, stdout=stdout, stderr=stderr,
			universal_newlines=False, bufsize=bufsize, **kwargs)


class AbstractChildWatcher(_AbstractChildWatcher):
	def add_child_handler(self, pid, callback, *args):
		raise NotImplementedError()

	def remove_child_handler(self, pid):
		raise NotImplementedError()

	def attach_loop(self, loop):
		raise NotImplementedError()

	def close(self):
		raise NotImplementedError()

	def __enter__(self):
		raise NotImplementedError()

	def __exit__(self, a, b, c):
		raise NotImplementedError()


class _PortageChildWatcher(_AbstractChildWatcher):
	def __init__(self, loop):
		"""
		@type loop: EventLoop
		@param loop: an instance of portage's internal event loop
		"""
		self._loop = loop
		self._callbacks = {}

	def close(self):
		pass

	def __enter__(self):
		return self

	def __exit__(self, a, b, c):
		pass

	def _child_exit(self, pid, status, data):
		self._callbacks.pop(pid)
		callback, args = data
		callback(pid, self._compute_returncode(status), *args)

	def _compute_returncode(self, status):
		if os.WIFSIGNALED(status):
			return -os.WTERMSIG(status)
		elif os.WIFEXITED(status):
			return os.WEXITSTATUS(status)
		else:
			return status

	def add_child_handler(self, pid, callback, *args):
		"""
		Register a new child handler.

		Arrange for callback(pid, returncode, *args) to be called when
		process 'pid' terminates. Specifying another callback for the same
		process replaces the previous handler.
		"""
		source_id = self._callbacks.get(pid)
		if source_id is not None:
			self._loop.source_remove(source_id)
		self._callbacks[pid] = self._loop.child_watch_add(
			pid, self._child_exit, data=(callback, args))

	def remove_child_handler(self, pid):
		"""
		Removes the handler for process 'pid'.

		The function returns True if the handler was successfully removed,
		False if there was nothing to remove.
		"""
		source_id = self._callbacks.pop(pid, None)
		if source_id is not None:
			return self._loop.source_remove(source_id)
		return False


class _PortageEventLoopPolicy(events.AbstractEventLoopPolicy):
	"""
	Implementation of asyncio.AbstractEventLoopPolicy based on portage's
	internal event loop. This supports running event loops in forks,
	which is not supported by the default asyncio event loop policy,
	see https://bugs.python.org/issue22087.
	"""
	def get_event_loop(self):
		"""
		Get the event loop for the current context.

		Returns an event loop object implementing the AbstractEventLoop
		interface.

		@rtype: asyncio.AbstractEventLoop (or compatible)
		@return: the current event loop policy
		"""
		return _global_event_loop()._asyncio_wrapper

	def get_child_watcher(self):
		"""Get the watcher for child processes."""
		return _global_event_loop()._asyncio_child_watcher


DefaultEventLoopPolicy = _PortageEventLoopPolicy
