# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'RetryError',
	'retry',
)

import functools

from portage.exception import PortageException
from portage.util.futures import asyncio


class RetryError(PortageException):
	"""Raised when retry fails."""
	def __init__(self):
		PortageException.__init__(self, "retry error")


def retry(try_max=None, try_timeout=None, overall_timeout=None,
	delay_func=None, reraise=False, loop=None):
	"""
	Create and return a retry decorator. The decorator is intended to
	operate only on a coroutine function.

	@param try_max: maximum number of tries
	@type try_max: int or None
	@param try_timeout: number of seconds to wait for a try to succeed
		before cancelling it, which is only effective if func returns
		tasks that support cancellation
	@type try_timeout: float or None
	@param overall_timeout: number of seconds to wait for retires to
		succeed before aborting, which is only effective if func returns
		tasks that support cancellation
	@type overall_timeout: float or None
	@param delay_func: function that takes an int argument corresponding
		to the number of previous tries and returns a number of seconds
		to wait before the next try
	@type delay_func: callable
	@param reraise: Reraise the last exception, instead of RetryError
	@type reraise: bool
	@param loop: event loop
	@type loop: EventLoop
	@return: func decorated with retry support
	@rtype: callable
	"""
	return functools.partial(_retry_wrapper, loop, try_max, try_timeout,
		overall_timeout, delay_func, reraise)


def _retry_wrapper(_loop, try_max, try_timeout, overall_timeout, delay_func,
	reraise, func, loop=None):
	"""
	Create and return a decorated function.
	"""
	return functools.partial(_retry, loop or _loop, try_max, try_timeout,
		overall_timeout, delay_func, reraise, func)


def _retry(loop, try_max, try_timeout, overall_timeout, delay_func,
	reraise, func, *args, **kwargs):
	"""
	Retry coroutine, used to implement retry decorator.

	@return: func return value
	@rtype: asyncio.Future (or compatible)
	"""
	loop = asyncio._wrap_loop(loop)
	future = loop.create_future()
	_Retry(future, loop, try_max, try_timeout, overall_timeout, delay_func,
		reraise, functools.partial(func, *args, **kwargs))
	return future


class _Retry:
	def __init__(self, future, loop, try_max, try_timeout, overall_timeout,
		delay_func, reraise, func):
		self._future = future
		self._loop = loop
		self._try_max = try_max
		self._try_timeout = try_timeout
		self._delay_func = delay_func
		self._reraise = reraise
		self._func = func

		self._try_timeout_handle = None
		self._overall_timeout_handle = None
		self._overall_timeout_expired = None
		self._tries = 0
		self._current_task = None
		self._previous_result = None

		future.add_done_callback(self._cancel_callback)
		if overall_timeout is not None:
			self._overall_timeout_handle = loop.call_later(
				overall_timeout, self._overall_timeout_callback)
		self._begin_try()

	def _cancel_callback(self, future):
		if future.cancelled() and self._current_task is not None:
			self._current_task.cancel()

	def _try_timeout_callback(self):
		self._try_timeout_handle = None
		self._current_task.cancel()

	def _overall_timeout_callback(self):
		self._overall_timeout_handle = None
		self._overall_timeout_expired = True
		self._current_task.cancel()
		self._retry_error()

	def _begin_try(self):
		self._tries += 1
		self._current_task = asyncio.ensure_future(self._func(), loop=self._loop)
		self._current_task.add_done_callback(self._try_done)
		if self._try_timeout is not None:
			self._try_timeout_handle = self._loop.call_later(
				self._try_timeout, self._try_timeout_callback)

	def _try_done(self, future):
		self._current_task = None

		if self._try_timeout_handle is not None:
			self._try_timeout_handle.cancel()
			self._try_timeout_handle = None

		if not future.cancelled():
			# consume exception, so that the event loop
			# exception handler does not report it
			future.exception()

		if self._overall_timeout_expired:
			return

		try:
			if self._future.cancelled():
				return

			self._previous_result = future
			if not (future.cancelled() or future.exception() is not None):
				# success
				self._future.set_result(future.result())
				return
		finally:
			if self._future.done() and self._overall_timeout_handle is not None:
				self._overall_timeout_handle.cancel()
				self._overall_timeout_handle = None

		if self._try_max is not None and self._tries >= self._try_max:
			self._retry_error()
			return

		if self._delay_func is not None:
			delay = self._delay_func(self._tries)
			self._current_task = self._loop.call_later(delay, self._delay_done)
			return

		self._begin_try()

	def _delay_done(self):
		self._current_task = None

		if self._future.cancelled() or self._overall_timeout_expired:
			return

		self._begin_try()

	def _retry_error(self):
		if self._previous_result is None or self._previous_result.cancelled():
			cause = asyncio.TimeoutError()
		else:
			cause = self._previous_result.exception()

		if self._reraise:
			e = cause
		else:
			e = RetryError()
			e.__cause__ = cause

		self._future.set_exception(e)
