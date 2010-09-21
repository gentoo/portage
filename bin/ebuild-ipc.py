#!/usr/bin/python
# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#
# This is a helper which ebuild processes can use
# to communicate with portage's main python process.

import logging
import os
import pickle
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

	def _wait(self, pid, msg):
		"""
		Wait on pid and return an appropriate exit code. This
		may return unsuccessfully due to timeout if the daemon
		process does not appear to be alive.
		"""

		start_time = time.time()
		wait_retval = None

		while True:
			try:
				try:
					portage.exception.AlarmSignal.register(
						self._COMMUNICATE_RETRY_TIMEOUT_SECONDS)
					wait_retval = os.waitpid(pid, 0)
					break
				finally:
					portage.exception.AlarmSignal.unregister()
			except OSError as e:
				# waitpid() raised an exception
				portage.util.writemsg_level(
					"ebuild-ipc: %s: %s\n" % (msg, e),
					level=logging.ERROR, noiselevel=-1)
				return 2
			except portage.exception.AlarmSignal:
				if wait_retval is not None:
					break
				elif self._daemon_is_alive():
					self._timeout_retry_msg(start_time, msg)
				else:
					self._no_daemon_msg()
					try:
						os.kill(pid, signal.SIGKILL)
						os.wait()
					except OSError as e:
						portage.util.writemsg_level(
							"ebuild-ipc: %s\n" % (e,),
							level=logging.ERROR, noiselevel=-1)
					return 2

		if not os.WIFEXITED(wait_retval[1]):
			portage.util.writemsg_level(
				"ebuild-ipc: %s: %s\n" % (msg,
				portage.localization._('subprocess failure: %s') % \
				wait_retval[1]),
				level=logging.ERROR, noiselevel=-1)
			return 2

		return os.WEXITSTATUS(wait_retval[1])

	def _receive_reply(self):

		# File streams are in unbuffered mode since we do atomic
		# read and write of whole pickles.
		input_file = open(self.ipc_out_fifo, 'rb', 0)
		data = input_file.read()

		retval = 2

		if not data:

			portage.util.writemsg_level(
				"ebuild-ipc: %s\n" % \
				(portage.localization._('read failed'),),
				level=logging.ERROR, noiselevel=-1)

		else:

			try:
				reply = pickle.loads(data)
			except SystemExit:
				raise
			except Exception as e:
				# The pickle module can raise practically
				# any exception when given corrupt data.
				portage.util.writemsg_level(
					"ebuild-ipc: %s\n" % (e,),
					level=logging.ERROR, noiselevel=-1)

			else:

				(out, err, retval) = reply

				if out:
					portage.util.writemsg_stdout(out, noiselevel=-1)

				if err:
					portage.util.writemsg(err, noiselevel=-1)

		return retval

	def _communicate(self, args):

		if not self._daemon_is_alive():
			self._no_daemon_msg()
			return 2

		# Use forks so that the child process can handle blocking IO
		# un-interrupted, while the parent handles all timeout
		# considerations. This helps to avoid possible race conditions
		# from interference between timeouts and blocking IO operations.
		pid = os.fork()

		if pid == 0:

			# File streams are in unbuffered mode since we do atomic
			# read and write of whole pickles.
			output_file = open(self.ipc_in_fifo, 'wb', 0)
			output_file.write(pickle.dumps(args))
			output_file.close()
			os._exit(os.EX_OK)

		msg = portage.localization._('during write')
		retval = self._wait(pid, msg)
		if retval != os.EX_OK:
			portage.util.writemsg_level(
				"ebuild-ipc: %s: %s\n" % (msg,
				portage.localization._('subprocess failure: %s') % \
				retval), level=logging.ERROR, noiselevel=-1)
			return retval

		if not self._daemon_is_alive():
			self._no_daemon_msg()
			return 2

		pid = os.fork()

		if pid == 0:
			retval = self._receive_reply()
			os._exit(retval)

		return self._wait(pid, portage.localization._('during read'))

def ebuild_ipc_main(args):
	ebuild_ipc = EbuildIpc()
	return ebuild_ipc.communicate(args)

if __name__ == '__main__':
	sys.exit(ebuild_ipc_main(sys.argv[1:]))
