# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import logging
import pickle
from portage import os
from portage.localization import _
from portage.util import writemsg_level
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
		# Read the whole pickle in a single atomic read() call.
		data = None
		if event & PollConstants.POLLIN:
			# For maximum portability, use os.read() here since
			# array.fromfile() and file.read() are both known to
			# erroneously return an empty string from this
			# non-blocking fifo stream on FreeBSD (bug #337465).
			try:
				data = os.read(fd, self._bufsize)
			except OSError as e:
				if e.errno != errno.EAGAIN:
					raise
				# Assume that another event will be generated
				# if there's any relevant data.

		if data:

			try:
				obj = pickle.loads(data)
			except SystemExit:
				raise
			except Exception:
				# The pickle module can raise practically
				# any exception when given corrupt data.
				pass
			else:

				self._reopen_input()

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
		# File streams are in unbuffered mode since we do atomic
		# read and write of whole pickles. Use non-blocking mode so
		# we don't hang if the client is killed before we can send
		# the reply. We rely on the client opening the other side
		# of this fifo before it sends its request, since otherwise
		# we'd have a race condition with this open call raising
		# ENXIO if the client hasn't opened the fifo yet.
		try:
			output_fd = os.open(self.output_fifo,
				os.O_WRONLY | os.O_NONBLOCK)
			try:
				os.write(output_fd, pickle.dumps(reply))
			finally:
				os.close(output_fd)
		except OSError as e:
			# This probably means that the client has been killed,
			# which causes open to fail with ENXIO.
			writemsg_level(
				"!!! EbuildIpcDaemon %s: %s\n" % \
				(_('failed to send reply'), e),
				level=logging.ERROR, noiselevel=-1)
