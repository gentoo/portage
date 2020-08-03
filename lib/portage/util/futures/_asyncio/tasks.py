# Copyright 2018-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

___all___ = (
	'ALL_COMPLETED',
	'FIRST_COMPLETED',
	'FIRST_EXCEPTION',
	'wait',
)

from asyncio import ALL_COMPLETED, FIRST_COMPLETED, FIRST_EXCEPTION

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util.futures:asyncio',
)

def wait(futures, loop=None, timeout=None, return_when=ALL_COMPLETED):
	"""
	Use portage's internal EventLoop to emulate asyncio.wait:
	https://docs.python.org/3/library/asyncio-task.html#asyncio.wait

	@param futures: futures to wait for
	@type futures: asyncio.Future (or compatible)
	@param timeout: number of seconds to wait (wait indefinitely if
		not specified)
	@type timeout: int or float
	@param return_when: indicates when this function should return, must
		be one of the constants ALL_COMPLETED, FIRST_COMPLETED, or
		FIRST_EXCEPTION (default is ALL_COMPLETED)
	@type return_when: object
	@param loop: event loop
	@type loop: EventLoop
	@return: tuple of (done, pending).
	@rtype: asyncio.Future (or compatible)
	"""
	loop = asyncio._wrap_loop(loop)
	result_future = loop.create_future()
	_Waiter(futures, timeout, return_when, result_future, loop)
	return result_future


class _Waiter:
	def __init__(self, futures, timeout, return_when, result_future, loop):
		self._futures = futures
		self._completed = set()
		self._exceptions = set()
		self._return_when = return_when
		self._result_future = result_future
		self._loop = loop
		self._ready = False
		self._timeout = None
		result_future.add_done_callback(self._cancel_callback)
		for future in self._futures:
			future.add_done_callback(self._done_callback)
		if timeout is not None:
			self._timeout = loop.call_later(timeout, self._timeout_callback)

	def _cancel_callback(self, future):
		if future.cancelled():
			self._ready_callback()

	def _timeout_callback(self):
		if not self._ready:
			self._ready = True
			self._ready_callback()

	def _done_callback(self, future):
		if future.cancelled() or future.exception() is None:
			self._completed.add(id(future))
		else:
			self._exceptions.add(id(future))
		if not self._ready and (
			(self._return_when is FIRST_COMPLETED and self._completed) or
			(self._return_when is FIRST_EXCEPTION and self._exceptions) or
			(len(self._futures) == len(self._completed) + len(self._exceptions))):
			self._ready = True
			# use call_soon in case multiple callbacks complete in quick succession
			self._loop.call_soon(self._ready_callback)

	def _ready_callback(self):
		if self._timeout is not None:
			self._timeout.cancel()
			self._timeout = None
		if self._result_future.cancelled():
			return
		done = []
		pending = []
		done_ids = self._completed.union(self._exceptions)
		for future in self._futures:
			if id(future) in done_ids:
				done.append(future)
			else:
				pending.append(future)
				future.remove_done_callback(self._done_callback)
		self._result_future.set_result((set(done), set(pending)))
