# Copyright 2012-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

try:
	import threading
except ImportError:
	# dummy_threading will not suffice
	threading = None

from portage import os
from _emerge.AbstractPollTask import AbstractPollTask

class PipeReaderBlockingIO(AbstractPollTask):
	"""
	Reads output from one or more files and saves it in memory, for
	retrieval via the getvalue() method. This is driven by a thread
	for each input file, in order to support blocking IO.  This may
	be useful for using threads to handle blocking IO with Jython,
	since Jython lacks the fcntl module which is needed for
	non-blocking IO (see http://bugs.jython.org/issue1074).
	"""

	__slots__ = ("input_files", "_read_data", "_terminate",
		"_threads", "_thread_rlock")

	def _start(self):
		self._terminate = threading.Event()
		self._threads = {}
		self._read_data = []

		self._registered = True
		self._thread_rlock = threading.RLock()
		with self._thread_rlock:
			for f in self.input_files.values():
				t = threading.Thread(target=self._reader_thread, args=(f,))
				t.daemon = True
				t.start()
				self._threads[f] = t

	def _reader_thread(self, f):
		try:
			terminated = self._terminate.is_set
		except AttributeError:
			# Jython 2.7.0a2
			terminated = self._terminate.isSet
		bufsize = self._bufsize
		while not terminated():
			buf = f.read(bufsize)
			with self._thread_rlock:
				if terminated():
					break
				elif buf:
					self._read_data.append(buf)
				else:
					del self._threads[f]
					if not self._threads:
						# Thread-safe callback to EventLoop
						self.scheduler.call_soon_threadsafe(self._eof)
					break
		f.close()

	def _eof(self):
		self._registered = False
		if self.returncode is None:
			self.returncode = os.EX_OK
		self._async_wait()

	def _cancel(self):
		self._terminate.set()
		self._registered = False
		if self.returncode is None:
			self.returncode = self._cancelled_returncode
		self._async_wait()

	def getvalue(self):
		"""Retrieve the entire contents"""
		with self._thread_rlock:
			return b''.join(self._read_data)

	def close(self):
		"""Free the memory buffer."""
		with self._thread_rlock:
			self._read_data = None
