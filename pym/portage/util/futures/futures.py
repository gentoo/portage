# Copyright 2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#
# For compatibility with python versions which do not have the
# asyncio module (Python 3.3 and earlier), this module provides a
# subset of the asyncio.futures.Futures interface.

from __future__ import unicode_literals

__all__ = (
	'CancelledError',
	'Future',
	'InvalidStateError',
)

try:
	from asyncio import (
		CancelledError,
		Future,
		InvalidStateError,
	)
except ImportError:

	from portage.exception import PortageException

	_PENDING = 'PENDING'
	_CANCELLED = 'CANCELLED'
	_FINISHED = 'FINISHED'

	class Error(PortageException):
		pass

	class CancelledError(Error):
		def __init__(self):
			Error.__init__(self, "cancelled")

	class InvalidStateError(Error):
		pass

	class Future(object):

		# Class variables serving as defaults for instance variables.
		_state = _PENDING
		_result = None
		_exception = None

		def cancel(self):
			"""Cancel the future and schedule callbacks.

			If the future is already done or cancelled, return False.  Otherwise,
			change the future's state to cancelled, schedule the callbacks and
			return True.
			"""
			if self._state != _PENDING:
				return False
			self._state = _CANCELLED
			return True

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

		def set_result(self, result):
			"""Mark the future done and set its result.

			If the future is already done when this method is called, raises
			InvalidStateError.
			"""
			if self._state != _PENDING:
				raise InvalidStateError('{}: {!r}'.format(self._state, self))
			self._result = result
			self._state = _FINISHED

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
