# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import time
class ProgressHandler:
	def __init__(self):
		self.curval = 0
		self.maxval = 0
		self._last_update = 0
		self.min_latency = 0.2

	def onProgress(self, maxval, curval):
		self.maxval = maxval
		self.curval = curval
		cur_time = time.time()
		if cur_time - self._last_update >= self.min_latency:
			self._last_update = cur_time
			self.display()

	def display(self):
		raise NotImplementedError(self)
