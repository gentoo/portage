# Copyright 2018-2021 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import functools

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util.futures:asyncio',
)

# A marker for iscoroutinefunction.
_is_coroutine = object()


def _iscoroutinefunction(func):
	"""
	Return True if func is a decorated coroutine function
	created with the coroutine decorator for this module.
	"""
	return getattr(func, '_is_coroutine', None) is _is_coroutine


def coroutine(generator_func):
	"""
	A decorator for a generator function that behaves as coroutine function.
	The generator should yield a Future instance in order to wait for it,
	and the result becomes the result of the current yield-expression,
	via the PEP 342 generator send() method.

	The decorated function returns a Future which is done when the generator
	is exhausted. The generator can return a value via the coroutine_return
	function.

	@param generator_func: A generator function that yields Futures, and
		will receive the result of each Future as the result of the
		corresponding yield-expression.
	@type generator_func: function
	@rtype: function
	@return: A function which calls the given generator function and
		returns a Future that is done when the generator is exhausted.
	"""
	# Note that functools.partial does not work for decoration of
	# methods, since it doesn't implement the descriptor protocol.
	# This problem is solve by defining a wrapper function.
	@functools.wraps(generator_func)
	def wrapped(*args, **kwargs):
		return _generator_future(generator_func, *args, **kwargs)
	wrapped._is_coroutine = _is_coroutine
	return wrapped


def coroutine_return(result=None):
	"""
	Terminate the current coroutine and set the result of the associated
	Future.

	@param result: of the current coroutine's Future
	@type object
	"""
	raise _CoroutineReturnValue(result)


def _generator_future(generator_func, *args, **kwargs):
	"""
	Call generator_func with the given arguments, and return a Future
	that is done when the resulting generation is exhausted. If a
	keyword argument named 'loop' is given, then it is used instead of
	the default event loop.
	"""
	loop = kwargs.get('loop')
	loop = asyncio._wrap_loop(loop)
	result = loop.create_future()
	_GeneratorTask(generator_func(*args, **kwargs), result, loop=loop)
	return result


class _CoroutineReturnValue(Exception):
	def __init__(self, result):
		self.result = result


class _GeneratorTask:
	"""
	Asynchronously executes the generator to completion, waiting for
	the result of each Future that it yields, and sending the result
	to the generator.
	"""
	def __init__(self, generator, result, loop):
		self._generator = generator
		self._result = result
		self._current_task = None
		self._loop = loop
		result.add_done_callback(self._cancel_callback)
		loop.call_soon(self._next)

	def _cancel_callback(self, result):
		if result.cancelled() and self._current_task is not None:
			# The done callback for self._current_task invokes
			# _next in either case here.
			self._current_task.done() or self._current_task.cancel()

	def _next(self, previous=None):
		self._current_task = None
		if self._result.cancelled():
			if previous is not None:
				# Consume exceptions, in order to avoid triggering
				# the event loop's exception handler.
				previous.cancelled() or previous.exception()

			# This will throw asyncio.CancelledError in the coroutine if
			# there's an opportunity (yield) before the generator raises
			# StopIteration.
			previous = self._result
		try:
			if previous is None:
				future = next(self._generator)
			elif previous.cancelled():
				future = self._generator.throw(asyncio.CancelledError())
			elif previous.exception() is None:
				future = self._generator.send(previous.result())
			else:
				future = self._generator.throw(previous.exception())

		except asyncio.CancelledError:
			self._result.cancel()
		except _CoroutineReturnValue as e:
			if not self._result.cancelled():
				self._result.set_result(e.result)
		except StopIteration:
			if not self._result.cancelled():
				self._result.set_result(None)
		except Exception as e:
			if not self._result.cancelled():
				self._result.set_exception(e)
		else:
			self._current_task = asyncio.ensure_future(future, loop=self._loop)
			self._current_task.add_done_callback(self._next)
