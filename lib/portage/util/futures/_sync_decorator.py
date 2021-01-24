# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util.futures:asyncio',
)


def _sync_decorator(func, loop=None):
	"""
	Decorate an asynchronous function (either a corouting function or a
	function that returns a Future) with a wrapper that runs the function
	synchronously.
	"""
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		return (loop or asyncio.get_event_loop()).run_until_complete(func(*args, **kwargs))
	return wrapper


def _sync_methods(obj, loop=None):
	"""
	For use with synchronous code that needs to interact with an object
	that has coroutine methods, this function generates a proxy which
	conveniently converts coroutine methods into synchronous methods.
	This allows coroutines to smoothly blend with synchronous
	code, eliminating clutter that might otherwise discourage the
	proliferation of coroutine usage for I/O bound tasks.
	"""
	loop = asyncio._wrap_loop(loop)
	return _ObjectAttrWrapper(obj,
		lambda attr: _sync_decorator(attr, loop=loop)
		if asyncio.iscoroutinefunction(attr) else attr)


class _ObjectAttrWrapper(portage.proxy.objectproxy.ObjectProxy):

	__slots__ = ('_obj', '_attr_wrapper')

	def __init__(self, obj, attr_wrapper):
		object.__setattr__(self, '_obj', obj)
		object.__setattr__(self, '_attr_wrapper', attr_wrapper)

	def __getattribute__(self, attr):
		obj = object.__getattribute__(self, '_obj')
		attr_wrapper = object.__getattribute__(self, '_attr_wrapper')
		return attr_wrapper(getattr(obj, attr))

	def _get_target(self):
		return object.__getattribute__(self, '_obj')
