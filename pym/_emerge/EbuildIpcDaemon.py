# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
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
       left orphan processes running in the background (as in bug #278895).

    4) Detect cases in which bash has exited unexpectedly (as in bug #190128).
	"""

	__slots__ = ('commands',)

	def _input_handler(self, fd, event):

		if event & PollConstants.POLLIN:

			# Read the whole pickle in a single read() call since
			# this stream is in non-blocking mode and pickle.load()
			# has been known to raise the following exception when
			# reading from a non-blocking stream:
			#
			#   File "/usr/lib64/python2.6/pickle.py", line 1370, in load
			#     return Unpickler(file).load()
			#   File "/usr/lib64/python2.6/pickle.py", line 858, in load
			#     dispatch[key](self)
			#   File "/usr/lib64/python2.6/pickle.py", line 1195, in load_setitem
			#     value = stack.pop()
			# IndexError: pop from empty list

			pickle_str = self._files.pipe_in.read()

			try:
				obj = pickle.loads(pickle_str)
			except (EnvironmentError, EOFError, ValueError,
				pickle.UnpicklingError):
				pass
			else:
				cmd_key = obj[0]
				cmd_handler = self.commands[cmd_key]
				reply = cmd_handler(obj)
				try:
					self._send_reply(reply)
				except OSError as e:
					if e.errno == errno.ENXIO:
						# This happens if the client side has been killed.
						pass
					else:
						raise

				# Allow the command to execute hooks after its reply
				# has been sent. This hook is used by the 'exit'
				# command to kill the ebuild process. For some
				# reason, the ebuild-ipc helper hangs up the
				# ebuild process if it is waiting for a reply
				# when we try to kill the ebuild process.
				reply_hook = getattr(cmd_handler,
					'reply_hook', None)
				if reply_hook is not None:
					reply_hook()

	def _send_reply(self, reply):
		output_fd = os.open(self.output_fifo, os.O_WRONLY|os.O_NONBLOCK)

		# File streams are in unbuffered mode since we do atomic
		# read and write of whole pickles.
		output_file = os.fdopen(output_fd, 'wb', 0)

		# Write the whole pickle in a single atomic write() call,
		# since the reader is in non-blocking mode and we want
		# it to get the whole pickle at once.
		output_file.write(pickle.dumps(reply))
		output_file.flush()
		output_file.close()
