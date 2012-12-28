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

def LoadLibrary(name):
	"""
	Calls ctypes.cdll.LoadLibrary(name) if the ctypes module is available,
	and otherwise returns None. Results are not cached, since that can
	cause problems when libraries are updated (see bug #448858).
	"""
	handle = None

	if ctypes is not None:
		handle = ctypes.cdll.LoadLibrary(name)

	return handle
