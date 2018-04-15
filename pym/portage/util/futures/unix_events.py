# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'AbstractChildWatcher',
	'DefaultEventLoopPolicy',
)

try:
	from asyncio.base_subprocess import BaseSubprocessTransport as _BaseSubprocessTransport
	from asyncio.unix_events import AbstractChildWatcher as _AbstractChildWatcher
except ImportError:
	_AbstractChildWatcher = object
	_BaseSubprocessTransport = object

import functools
import os
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

		if subprocess.PIPE in (stdin, stdout, stderr):
			# Requires connect_read/write_pipe implementation, for example
			# see asyncio.unix_events._UnixReadPipeTransport.
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
