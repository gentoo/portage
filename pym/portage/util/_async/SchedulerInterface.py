# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import gzip
import errno

from portage import _encodings
from portage import _unicode_encode
from portage.util import writemsg_level
from ..SlotObject import SlotObject

class SchedulerInterface(SlotObject):

	__slots__ = ("IO_ERR", "IO_HUP", "IO_IN", "IO_NVAL", "IO_OUT", "IO_PRI",
		"child_watch_add", "idle_add", "io_add_watch", "iteration",
		"source_remove", "timeout_add", "_event_loop", "_is_background")

	def __init__(self, event_loop, is_background=None, **kwargs):
		SlotObject.__init__(self, **kwargs)
		self._event_loop = event_loop
		if is_background is None:
			is_background = self._return_false
		self._is_background = is_background
		self.IO_ERR = event_loop.IO_ERR
		self.IO_HUP = event_loop.IO_HUP
		self.IO_IN = event_loop.IO_IN
		self.IO_NVAL = event_loop.IO_NVAL
		self.IO_OUT = event_loop.IO_OUT
		self.IO_PRI = event_loop.IO_PRI
		self.child_watch_add = event_loop.child_watch_add
		self.idle_add = event_loop.idle_add
		self.io_add_watch = event_loop.io_add_watch
		self.iteration = event_loop.iteration
		self.source_remove = event_loop.source_remove
		self.timeout_add = event_loop.timeout_add

	@staticmethod
	def _return_false():
		return False

	def output(self, msg, log_path=None, background=None,
		level=0, noiselevel=-1):
		"""
		Output msg to stdout if not self._is_background(). If log_path
		is not None then append msg to the log (appends with
		compression if the filename extension of log_path corresponds
		to a supported compression type).
		"""

		global_background = self._is_background()
		if background is None or global_background:
			# Use the global value if the task does not have a local
			# background value. For example, parallel-fetch tasks run
			# in the background while other tasks concurrently run in
			# the foreground.
			background = global_background

		msg_shown = False
		if not background:
			writemsg_level(msg, level=level, noiselevel=noiselevel)
			msg_shown = True

		if log_path is not None:
			try:
				f = open(_unicode_encode(log_path,
					encoding=_encodings['fs'], errors='strict'),
					mode='ab')
				f_real = f
			except IOError as e:
				if e.errno not in (errno.ENOENT, errno.ESTALE):
					raise
				if not msg_shown:
					writemsg_level(msg, level=level, noiselevel=noiselevel)
			else:

				if log_path.endswith('.gz'):
					# NOTE: The empty filename argument prevents us from
					# triggering a bug in python3 which causes GzipFile
					# to raise AttributeError if fileobj.name is bytes
					# instead of unicode.
					f =  gzip.GzipFile(filename='', mode='ab', fileobj=f)

				f.write(_unicode_encode(msg))
				f.close()
				if f_real is not f:
					f_real.close()
