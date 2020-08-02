# Copyright 2012-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

from .EventLoop import EventLoop
from portage.util._eventloop.asyncio_event_loop import AsyncioEventLoop


_MAIN_PID = os.getpid()
_instances = {}


def global_event_loop():
	"""
	Get a global EventLoop (or compatible object) instance which
	belongs exclusively to the current process.
	"""

	pid = os.getpid()
	instance = _instances.get(pid)
	if instance is not None:
		return instance

	constructor = AsyncioEventLoop
	# If the default constructor doesn't support multiprocessing,
	# then multiprocessing constructor is used in subprocesses.
	if not constructor.supports_multiprocessing and pid != _MAIN_PID:
		constructor = EventLoop

	# Use the _asyncio_wrapper attribute, so that unit tests can compare
	# the reference to one retured from _wrap_loop(), since they should
	# not close the loop if it refers to a global event loop.
	instance = constructor()._asyncio_wrapper
	_instances[pid] = instance
	return instance
