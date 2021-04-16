# Copyright 2012-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import gzip
import errno

from portage import _encodings
from portage import _unicode_encode
from portage.util import writemsg_level
from portage.util.futures._asyncio.streams import _writer
from ..SlotObject import SlotObject

class SchedulerInterface(SlotObject):

	_event_loop_attrs = (
		"add_reader",
		"add_writer",
		"call_at",
		"call_exception_handler",
		"call_later",
		"call_soon",
		"call_soon_threadsafe",
		"close",
		"create_future",
		"default_exception_handler",
		"get_debug",
		"is_closed",
		"is_running",
		"remove_reader",
		"remove_writer",
		"run_in_executor",
		"run_until_complete",
		"set_debug",
		"time",

		"_asyncio_child_watcher",
		# This attribute it used by _wrap_loop to detect if the
		# loop already has a suitable wrapper.
		"_asyncio_wrapper",
	)

	__slots__ = _event_loop_attrs + ("_event_loop", "_is_background")

	def __init__(self, event_loop, is_background=None, **kwargs):
		SlotObject.__init__(self, **kwargs)
		self._event_loop = event_loop
		if is_background is None:
			is_background = self._return_false
		self._is_background = is_background
		for k in self._event_loop_attrs:
			setattr(self, k, getattr(event_loop, k))

	@staticmethod
	def _return_false():
		return False

	async def async_output(self, msg, log_file=None, background=None,
		level=0, noiselevel=-1):
		"""
		Output a msg to stdio (if not in background) and to a log file
		if provided.

		@param msg: a message string, including newline if appropriate
		@type msg: str
		@param log_file: log file in binary mode
		@type log_file: file
		@param background: send messages only to log (not to stdio)
		@type background: bool
		@param level: a numeric logging level (see the logging module)
		@type level: int
		@param noiselevel: passed directly to writemsg
		@type noiselevel: int
		"""
		global_background = self._is_background()
		if background is None or global_background:
			background = global_background

		if not background:
			writemsg_level(msg, level=level, noiselevel=noiselevel)

		if log_file is not None:
			await _writer(log_file, _unicode_encode(msg))

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
