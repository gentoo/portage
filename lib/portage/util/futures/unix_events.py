# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'AbstractChildWatcher',
	'DefaultEventLoopPolicy',
)

import asyncio as _real_asyncio
from asyncio import events
from asyncio.unix_events import AbstractChildWatcher

import fcntl
import os

from portage.util._eventloop.global_event_loop import (
	global_event_loop as _global_event_loop,
)


if hasattr(os, 'set_blocking'):
	def _set_nonblocking(fd):
		os.set_blocking(fd, False)
else:
	def _set_nonblocking(fd):
		flags = fcntl.fcntl(fd, fcntl.F_GETFL)
		flags = flags | os.O_NONBLOCK
		fcntl.fcntl(fd, fcntl.F_SETFL, flags)


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
