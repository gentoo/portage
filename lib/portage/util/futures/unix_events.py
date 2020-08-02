# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'AbstractChildWatcher',
	'DefaultEventLoopPolicy',
)

import asyncio as _real_asyncio
from asyncio.base_subprocess import BaseSubprocessTransport as _BaseSubprocessTransport
from asyncio.unix_events import AbstractChildWatcher as _AbstractChildWatcher
from asyncio.transports import (
	ReadTransport as _ReadTransport,
	WriteTransport as _WriteTransport,
)

import errno
import fcntl
import functools
import logging
import os
import socket
import stat
import subprocess
import sys

from portage.util._eventloop.global_event_loop import (
	global_event_loop as _global_event_loop,
)
from portage.util.futures import (
	asyncio,
	events,
)

from portage.util.futures.transports import _FlowControlMixin


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
		self.run_until_complete = loop.run_until_complete
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

	@property
	def _asyncio_child_watcher(self):
		"""
		In order to avoid accessing the internal _loop attribute, portage
		internals should use this property when possible.

		@rtype: asyncio.AbstractChildWatcher
		@return: the internal event loop's AbstractChildWatcher interface
		"""
		return self._loop._asyncio_child_watcher

	@property
	def _asyncio_wrapper(self):
		"""
		In order to avoid accessing the internal _loop attribute, portage
		internals should use this property when possible.

		@rtype: asyncio.AbstractEventLoop
		@return: the internal event loop's AbstractEventLoop interface
		"""
		return self

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

	def connect_write_pipe(self, protocol_factory, pipe):
		"""
		Register write pipe in event loop. Set the pipe to non-blocking mode.

		@type protocol_factory: callable
		@param protocol_factory: must instantiate object with Protocol interface
		@type pipe: file
		@param pipe: a pipe to write to
		@rtype: asyncio.Future
		@return: Return pair (transport, protocol), where transport supports the
			WriteTransport interface.
		"""
		protocol = protocol_factory()
		result = self.create_future()
		waiter = self.create_future()
		transport = self._make_write_pipe_transport(pipe, protocol, waiter)

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

	def _make_write_pipe_transport(self, pipe, protocol, waiter=None,
								   extra=None):
		return _UnixWritePipeTransport(self, pipe, protocol, waiter, extra)

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


class _UnixWritePipeTransport(_FlowControlMixin, _WriteTransport):
	"""
	This is identical to the standard library's private
	asyncio.unix_events._UnixWritePipeTransport class, except that it
	only calls public AbstractEventLoop methods.
	"""

	def __init__(self, loop, pipe, protocol, waiter=None, extra=None):
		super().__init__(extra, loop)
		self._extra['pipe'] = pipe
		self._pipe = pipe
		self._fileno = pipe.fileno()
		self._protocol = protocol
		self._buffer = bytearray()
		self._conn_lost = 0
		self._closing = False  # Set when close() or write_eof() called.

		mode = os.fstat(self._fileno).st_mode
		is_char = stat.S_ISCHR(mode)
		is_fifo = stat.S_ISFIFO(mode)
		is_socket = stat.S_ISSOCK(mode)
		if not (is_char or is_fifo or is_socket):
			self._pipe = None
			self._fileno = None
			self._protocol = None
			raise ValueError("Pipe transport is only for "
							 "pipes, sockets and character devices")

		_set_nonblocking(self._fileno)
		self._loop.call_soon(self._protocol.connection_made, self)

		# On AIX, the reader trick (to be notified when the read end of the
		# socket is closed) only works for sockets. On other platforms it
		# works for pipes and sockets. (Exception: OS X 10.4?  Issue #19294.)
		if is_socket or (is_fifo and not sys.platform.startswith("aix")):
			# only start reading when connection_made() has been called
			self._loop.call_soon(self._loop.add_reader,
								 self._fileno, self._read_ready)

		if waiter is not None:
			# only wake up the waiter when connection_made() has been called
			self._loop.call_soon(
				lambda: None if waiter.cancelled() else waiter.set_result(None))

	def get_write_buffer_size(self):
		return len(self._buffer)

	def _read_ready(self):
		# Pipe was closed by peer.
		if self._loop.get_debug():
			logging.info("%r was closed by peer", self)
		if self._buffer:
			self._close(BrokenPipeError())
		else:
			self._close()

	def write(self, data):
		assert isinstance(data, (bytes, bytearray, memoryview)), repr(data)
		if isinstance(data, bytearray):
			data = memoryview(data)
		if not data:
			return

		if self._conn_lost or self._closing:
			self._conn_lost += 1
			return

		if not self._buffer:
			# Attempt to send it right away first.
			try:
				n = os.write(self._fileno, data)
			except (BlockingIOError, InterruptedError):
				n = 0
			except Exception as exc:
				self._conn_lost += 1
				self._fatal_error(exc, 'Fatal write error on pipe transport')
				return
			if n == len(data):
				return
			if n > 0:
				data = memoryview(data)[n:]
			self._loop.add_writer(self._fileno, self._write_ready)

		self._buffer += data
		self._maybe_pause_protocol()

	def _write_ready(self):
		assert self._buffer, 'Data should not be empty'

		try:
			n = os.write(self._fileno, self._buffer)
		except (BlockingIOError, InterruptedError):
			pass
		except Exception as exc:
			self._buffer.clear()
			self._conn_lost += 1
			# Remove writer here, _fatal_error() doesn't it
			# because _buffer is empty.
			self._loop.remove_writer(self._fileno)
			self._fatal_error(exc, 'Fatal write error on pipe transport')
		else:
			if n == len(self._buffer):
				self._buffer.clear()
				self._loop.remove_writer(self._fileno)
				self._maybe_resume_protocol()  # May append to buffer.
				if self._closing:
					self._loop.remove_reader(self._fileno)
					self._call_connection_lost(None)
				return
			if n > 0:
				del self._buffer[:n]

	def can_write_eof(self):
		return True

	def write_eof(self):
		if self._closing:
			return
		assert self._pipe
		self._closing = True
		if not self._buffer:
			self._loop.remove_reader(self._fileno)
			self._loop.call_soon(self._call_connection_lost, None)

	def set_protocol(self, protocol):
		self._protocol = protocol

	def get_protocol(self):
		return self._protocol

	def is_closing(self):
		return self._closing

	def close(self):
		if self._pipe is not None and not self._closing:
			# write_eof is all what we needed to close the write pipe
			self.write_eof()

	def abort(self):
		self._close(None)

	def _fatal_error(self, exc, message='Fatal error on pipe transport'):
		# should be called by exception handler only
		if isinstance(exc,
			(BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
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

	def _close(self, exc=None):
		self._closing = True
		if self._buffer:
			self._loop.remove_writer(self._fileno)
		self._buffer.clear()
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


if hasattr(os, 'set_inheritable'):
	# Python 3.4 and newer
	_set_inheritable = os.set_inheritable
else:
	def _set_inheritable(fd, inheritable):
		cloexec_flag = getattr(fcntl, 'FD_CLOEXEC', 1)

		old = fcntl.fcntl(fd, fcntl.F_GETFD)
		if not inheritable:
			fcntl.fcntl(fd, fcntl.F_SETFD, old | cloexec_flag)
		else:
			fcntl.fcntl(fd, fcntl.F_SETFD, old & ~cloexec_flag)


class _UnixSubprocessTransport(_BaseSubprocessTransport):
	"""
	This is identical to the standard library's private
	asyncio.unix_events._UnixSubprocessTransport class, except that it
	only calls public AbstractEventLoop methods.
	"""
	def _start(self, args, shell, stdin, stdout, stderr, bufsize, **kwargs):
		stdin_w = None
		if stdin == subprocess.PIPE:
			# Use a socket pair for stdin, since not all platforms
			# support selecting read events on the write end of a
			# socket (which we use in order to detect closing of the
			# other end).  Notably this is needed on AIX, and works
			# just fine on other platforms.
			stdin, stdin_w = socket.socketpair()

			# Mark the write end of the stdin pipe as non-inheritable,
			# needed by close_fds=False on Python 3.3 and older
			# (Python 3.4 implements the PEP 446, socketpair returns
			# non-inheritable sockets)
			_set_inheritable(stdin_w.fileno(), False)
		self._proc = subprocess.Popen(
			args, shell=shell, stdin=stdin, stdout=stdout, stderr=stderr,
			universal_newlines=False, bufsize=bufsize, **kwargs)
		if stdin_w is not None:
			stdin.close()
			self._proc.stdin = os.fdopen(stdin_w.detach(), 'wb', bufsize)


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
		if os.WIFEXITED(status):
			return os.WEXITSTATUS(status)
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


class _AsyncioEventLoopPolicy(_PortageEventLoopPolicy):
	"""
	A subclass of _PortageEventLoopPolicy which raises
	NotImplementedError if it is set as the real asyncio event loop
	policy, since this class is intended to *wrap* the real asyncio
	event loop policy.
	"""
	def _check_recursion(self):
		if _real_asyncio.get_event_loop_policy() is self:
			raise NotImplementedError('this class is only a wrapper')

	def get_event_loop(self):
		self._check_recursion()
		return super(_AsyncioEventLoopPolicy, self).get_event_loop()

	def get_child_watcher(self):
		self._check_recursion()
		return super(_AsyncioEventLoopPolicy, self).get_child_watcher()


DefaultEventLoopPolicy = _AsyncioEventLoopPolicy
