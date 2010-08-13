# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import array
import pickle
from portage import os
from _emerge.FifoIpcDaemon import FifoIpcDaemon
from _emerge.PollConstants import PollConstants

class EbuildIpcDaemon(FifoIpcDaemon):
	"""
    This class serves as an IPC daemon, which ebuild processes can use
    to communicate with portage's main python process.

    Here are a few possible uses:

    1) Robust subshell/subprocess die support. This allows the ebuild
       environment to reliably die without having to rely on signal IPC.

    2) Delegation of portageq calls to the main python process, eliminating
       performance and userpriv permission issues.

    3) Reliable ebuild termination in cases when the ebuild has accidentally
       left orphan processes running in the backgraound (as in bug 278895).
	"""

	__slots__ = ()

	def _input_handler(self, fd, event):

		if event & PollConstants.POLLIN:

			buf = array.array('B')
			try:
				buf.fromfile(self._files.pipe_in, self._bufsize)
			except (EOFError, IOError):
				pass

			if buf:
				obj = pickle.loads(buf.tostring())
				if isinstance(obj, list) and \
					obj and \
					obj[0] == 'exit':
					output_fd = os.open(self.output_fifo, os.O_WRONLY|os.O_NONBLOCK)
					output_file = os.fdopen(output_fd, 'wb')
					pickle.dump('OK', output_file)
					output_file.close()
					self._unregister()
					self.wait()

		self._unregister_if_appropriate(event)
		return self._registered
