#!/usr/bin/python
# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#
# This is a helper which ebuild processes can use
# to communicate with portage's main python process.

import array
import logging
import os
import pickle
import select
import signal
import sys
import time

def debug_signal(signum, frame):
	import pdb
	pdb.set_trace()
signal.signal(signal.SIGUSR1, debug_signal)

# Avoid sandbox violations after python upgrade.
pym_path = os.path.join(os.path.dirname(
	os.path.dirname(os.path.realpath(__file__))), "pym")
if os.environ.get("SANDBOX_ON") == "1":
	sandbox_write = os.environ.get("SANDBOX_WRITE", "").split(":")
	if pym_path not in sandbox_write:
		sandbox_write.append(pym_path)
		os.environ["SANDBOX_WRITE"] = \
			":".join(filter(None, sandbox_write))

import portage
portage._disable_legacy_globals()

class EbuildIpc(object):

	# Timeout for each individual communication attempt (we retry
	# as long as the daemon process appears to be alive).
	_COMMUNICATE_RETRY_TIMEOUT_SECONDS = 15
	_BUFSIZE = 4096

	def __init__(self):
		self.fifo_dir = os.environ['PORTAGE_BUILDDIR']
		self.ipc_in_fifo = os.path.join(self.fifo_dir, '.ipc_in')
		self.ipc_out_fifo = os.path.join(self.fifo_dir, '.ipc_out')
		self.ipc_lock_file = os.path.join(self.fifo_dir, '.ipc_lock')

	def _daemon_is_alive(self):
		try:
			builddir_lock = portage.locks.lockfile(self.fifo_dir,
				wantnewlockfile=True, flags=os.O_NONBLOCK)
		except portage.exception.TryAgain:
			return True
		else:
			portage.locks.unlockfile(builddir_lock)
			return False

	def communicate(self, args):

		# Make locks quiet since unintended locking messages displayed on
		# stdout could corrupt the intended output of this program.
		portage.locks._quiet = True
		lock_obj = portage.locks.lockfile(self.ipc_lock_file, unlinkfile=True)

		try:
			return self._communicate(args)
		finally:
			portage.locks.unlockfile(lock_obj)

	def _timeout_retry_msg(self, start_time, when):
		time_elapsed = time.time() - start_time
		portage.util.writemsg_level(
			portage.localization._(
			'ebuild-ipc timed out %s after %d seconds,' + \
			' retrying...\n') % (when, time_elapsed),
			level=logging.ERROR, noiselevel=-1)

	def _no_daemon_msg(self):
		portage.util.writemsg_level(
			portage.localization._(
			'ebuild-ipc: daemon process not detected\n'),
			level=logging.ERROR, noiselevel=-1)

	def _communicate(self, args):

		if not self._daemon_is_alive():
			self._no_daemon_msg()
			return 2

		start_time = time.time()

		# File streams are in unbuffered mode since we do atomic
		# read and write of whole pickles.
		input_fd = os.open(self.ipc_out_fifo,
			os.O_RDONLY|os.O_NONBLOCK)
		input_file = os.fdopen(input_fd, 'rb', 0)
		output_file = None

		while True:
			try:
				try:
					portage.exception.AlarmSignal.register(
						self._COMMUNICATE_RETRY_TIMEOUT_SECONDS)

					if output_file is not None:
						output_file.close()
						output_file = None

					output_file = open(self.ipc_in_fifo, 'wb', 0)

					# Write the whole pickle in a single atomic write() call,
					# since the reader is in non-blocking mode and we want
					# it to get the whole pickle at once.
					output_file.write(pickle.dumps(args))
					output_file.close()
					break
				finally:
					portage.exception.AlarmSignal.unregister()
			except portage.exception.AlarmSignal:
				if self._daemon_is_alive():
					self._timeout_retry_msg(start_time,
						portage.localization._('during write'))
				else:
					self._no_daemon_msg()
					return 2

		start_time = time.time()
		while True:
			events = select.select([input_file], [], [],
				self._COMMUNICATE_RETRY_TIMEOUT_SECONDS)
			if events[0]:
				break
			else:
				if self._daemon_is_alive():
					self._timeout_retry_msg(start_time,
						portage.localization._('during select'))
				else:
					self._no_daemon_msg()
					return 2

		start_time = time.time()
		while True:
			try:
				try:
					portage.exception.AlarmSignal.register(
						self._COMMUNICATE_RETRY_TIMEOUT_SECONDS)
					# Read the whole pickle in a single atomic read() call.
					buf = array.array('B')
					try:
						buf.fromfile(input_file, self._BUFSIZE)
					except (EOFError, IOError) as e:
						if not buf:
							portage.util.writemsg_level(
								"ebuild-ipc: %s\n" % (e,),
								level=logging.ERROR, noiselevel=-1)
					break
				finally:
					portage.exception.AlarmSignal.unregister()
			except portage.exception.AlarmSignal:
				if self._daemon_is_alive():
					self._timeout_retry_msg(start_time,
						portage.localization._('during read'))
				else:
					self._no_daemon_msg()
					return 2

		rval = 2

		if buf:

			try:
				reply = pickle.loads(buf.tostring())
			except (EnvironmentError, EOFError, ValueError,
				pickle.UnpicklingError) as e:
				portage.util.writemsg_level(
					"ebuild-ipc: %s\n" % (e,),
					level=logging.ERROR, noiselevel=-1)

			else:
				input_file.close()

				(out, err, rval) = reply

				if out:
					portage.util.writemsg_stdout(out, noiselevel=-1)

				if err:
					portage.util.writemsg(err, noiselevel=-1)

		return rval

def ebuild_ipc_main(args):
	ebuild_ipc = EbuildIpc()
	return ebuild_ipc.communicate(args)

if __name__ == '__main__':
	sys.exit(ebuild_ipc_main(sys.argv[1:]))
