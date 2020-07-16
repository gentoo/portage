# Copyright 2016-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#
# For compatibility with python versions which do not have the
# asyncio module (Python 3.3 and earlier), this module provides a
# subset of the asyncio.futures.Futures interface.

__all__ = (
	'CancelledError',
	'Future',
	'InvalidStateError',
	'TimeoutError',
)

try:
	from asyncio import (
		CancelledError,
		Future,
		InvalidStateError,
		TimeoutError,
	)
except ImportError:

	from portage.exception import PortageException

	class Error(PortageException):
		pass

	class CancelledError(Error):
		def __init__(self):
			Error.__init__(self, "cancelled")

	class TimeoutError(Error):
		def __init__(self):
			Error.__init__(self, "timed out")

	class InvalidStateError(Error):
		pass

	Future = None

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util._eventloop.global_event_loop:global_event_loop@_global_event_loop',
)

_PENDING = 'PENDING'
_CANCELLED = 'CANCELLED'
_FINISHED = 'FINISHED'

class _EventLoopFuture(object):
	"""
	This class provides (a subset of) the asyncio.Future interface, for
	use with the EventLoop class, because EventLoop is currently
	missing some of the asyncio.AbstractEventLoop methods that
	asyncio.Future requires.
	"""

	# Class variables serving as defaults for instance variables.
	_state = _PENDING
	_result = None
	_exception = None
	_loop = None

	def __init__(self, loop=None):
		"""Initialize the future.

		The optional loop argument allows explicitly setting the event
		loop object used by the future. If it's not provided, the future uses
		the default event loop.
		"""
		if loop is None:
			self._loop = _global_event_loop()
		else:
			self._loop = loop
		self._callbacks = []

	def cancel(self):
		"""Cancel the future and schedule callbacks.

		If the future is already done or cancelled, return False.  Otherwise,
		change the future's state to cancelled, schedule the callbacks and
		return True.
		"""
		if self._state != _PENDING:
			return False
		self._state = _CANCELLED
		self._schedule_callbacks()
		return True

	def _schedule_callbacks(self):
		"""Internal: Ask the event loop to call all callbacks.

		The callbacks are scheduled to be called as soon as possible. Also
		clears the callback list.
		"""
		callbacks = self._callbacks[:]
		if not callbacks:
			return

		self._callbacks[:] = []
		for callback in callbacks:
			self._loop.call_soon(callback, self)

	def cancelled(self):
		"""Return True if the future was cancelled."""
		return self._state == _CANCELLED

	def done(self):
		"""Return True if the future is done.

		Done means either that a result / exception are available, or that the
		future was cancelled.
		"""
		return self._state != _PENDING

	def result(self):
		"""Return the result this future represents.

		If the future has been cancelled, raises CancelledError.  If the
		future's result isn't yet available, raises InvalidStateError.  If
		the future is done and has an exception set, this exception is raised.
		"""
		if self._state == _CANCELLED:
			raise CancelledError()
		if self._state != _FINISHED:
			raise InvalidStateError('Result is not ready.')
		if self._exception is not None:
			raise self._exception
		return self._result

	def exception(self):
		"""Return the exception that was set on this future.

		The exception (or None if no exception was set) is returned only if
		the future is done.  If the future has been cancelled, raises
		CancelledError.  If the future isn't done yet, raises
		InvalidStateError.
		"""
		if self._state == _CANCELLED:
			raise CancelledError
		if self._state != _FINISHED:
			raise InvalidStateError('Exception is not set.')
		return self._exception

	def add_done_callback(self, fn):
		"""Add a callback to be run when the future becomes done.

		The callback is called with a single argument - the future object. If
		the future is already done when this is called, the callback is
		scheduled with call_soon.
		"""
		if self._state != _PENDING:
			self._loop.call_soon(fn, self)
		else:
			self._callbacks.append(fn)

	def remove_done_callback(self, fn):
		"""Remove all instances of a callback from the "call when done" list.

		Returns the number of callbacks removed.
		"""
		filtered_callbacks = [f for f in self._callbacks if f != fn]
		removed_count = len(self._callbacks) - len(filtered_callbacks)
		if removed_count:
			self._callbacks[:] = filtered_callbacks
		return removed_count

	def set_result(self, result):
		"""Mark the future done and set its result.

		If the future is already done when this method is called, raises
		InvalidStateError.
		"""
		if self._state != _PENDING:
			raise InvalidStateError('{}: {!r}'.format(self._state, self))
		self._result = result
		self._state = _FINISHED
		self._schedule_callbacks()

	def set_exception(self, exception):
		"""Mark the future done and set an exception.

		If the future is already done when this method is called, raises
		InvalidStateError.
		"""
		if self._state != _PENDING:
			raise InvalidStateError('{}: {!r}'.format(self._state, self))
		if isinstance(exception, type):
			exception = exception()
		self._exception = exception
		self._state = _FINISHED
		self._schedule_callbacks()


if Future is None:
	Future = _EventLoopFuture
