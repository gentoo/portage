# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import time
import signal

import portage


class ProgressHandler:
	def __init__(self):
		self.reset()

	def reset(self):
		self.curval = 0
		self.maxval = 0
		self.last_update = 0
		self.min_display_latency = 0.2

	def onProgress(self, maxval, curval):
		self.maxval = maxval
		self.curval = curval
		cur_time = time.time()
		if cur_time - self.last_update >= self.min_display_latency:
			self.last_update = cur_time
			self.display()

	def display(self):
		raise NotImplementedError(self)


class ProgressBar(ProgressHandler):
	"""Class to set up and return a Progress Bar"""

	def __init__(self, isatty, **kwargs):
		self.isatty = isatty
		self.kwargs = kwargs
		ProgressHandler.__init__(self)
		self.progressBar = None

	def start(self):
		if self.isatty:
			self.progressBar = portage.output.TermProgressBar(**self.kwargs)
			signal.signal(signal.SIGWINCH, self.sigwinch_handler)
		else:
			self.onProgress = None
		return self.onProgress

	def set_label(self, _label):
		self.kwargs['label'] = _label

	def display(self):
		self.progressBar.set(self.curval, self.maxval)

	def sigwinch_handler(self, signum, frame):
		lines, self.progressBar.term_columns = \
			portage.output.get_term_size()

	def stop(self):
		signal.signal(signal.SIGWINCH, signal.SIG_DFL)
