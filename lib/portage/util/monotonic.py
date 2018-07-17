# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['monotonic']

import time
try:
	import threading
except ImportError:
	import dummy_threading as threading

monotonic = getattr(time, 'monotonic', None)

if monotonic is None:
	def monotonic():
		"""
		Emulate time.monotonic() which is available in Python 3.3 and later.

		@return: A float expressed in seconds since an epoch.
		"""
		with monotonic._lock:
			current = time.time() + monotonic._offset
			delta = current - monotonic._previous
			if delta < 0:
				monotonic._offset -= delta
				current = monotonic._previous
			else:
				monotonic._previous = current
			return current

	# offset is used to counteract any backward movements
	monotonic._offset = 0
	monotonic._previous = time.time()
	monotonic._lock = threading.Lock()
