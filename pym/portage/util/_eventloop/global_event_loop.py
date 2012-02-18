# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os

from .EventLoop import EventLoop

_default_constructor = EventLoop
#from .GlibEventLoop import GlibEventLoop as _default_constructor

# If _default_constructor doesn't support multiprocessing,
# then _multiprocessing_constructor is used in subprocesses.
_multiprocessing_constructor = EventLoop

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

	constructor = _default_constructor
	if not constructor.supports_multiprocessing and pid != _MAIN_PID:
		constructor = _multiprocessing_constructor

	instance = constructor()
	_instances[pid] = instance
	return instance
