# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

try:
	import ctypes
	import ctypes.util
except ImportError:
	ctypes = None
else:
	try:
		ctypes.cdll
	except AttributeError:
		ctypes = None

_library_names = {}

def find_library(name):
	"""
	Calls ctype.util.find_library() if the ctypes module is available,
	and otherwise returns None. Results are cached for future invocations.
	"""
	filename = _library_names.get(name)
	if filename is None:
		if ctypes is not None:
			filename = ctypes.util.find_library(name)
			if filename is None:
				filename = False
			_library_names[name] = filename

	if filename is False:
		return None
	return filename

_library_handles = {}

def LoadLibrary(name):
	"""
	Calls ctypes.cdll.LoadLibrary(name) if the ctypes module is available,
	and otherwise returns None. Results are cached for future invocations.
	"""
	handle = _library_handles.get(name)

	if handle is None and ctypes is not None:
		handle = ctypes.CDLL(name, use_errno=True)
		_library_handles[name] = handle

	return handle
