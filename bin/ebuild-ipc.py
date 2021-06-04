#!/usr/bin/python -b
# Copyright 2010-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
#
# This is a helper which ebuild processes can use
# to communicate with portage's main python process.

# This block ensures that ^C interrupts are handled quietly.
try:
	import os
	import signal

	def exithandler(signum, _frame):
		signal.signal(signum, signal.SIG_DFL)
		os.kill(os.getpid(), signum)

	signal.signal(signal.SIGINT, exithandler)
	signal.signal(signal.SIGTERM, exithandler)
	signal.signal(signal.SIGPIPE, signal.SIG_DFL)

except KeyboardInterrupt:
	raise SystemExit(130)

import errno
import logging
import pickle
import platform
import sys
import time

def debug_signal(signum, frame):
	import pdb
	pdb.set_trace()

if platform.python_implementation() == 'Jython':
	debug_signum = signal.SIGUSR2 # bug #424259
else:
	debug_signum = signal.SIGUSR1

signal.signal(debug_signum, debug_signal)

if os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), ".portage_not_installed")):
	pym_paths = [os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "lib")]
	sys.path.insert(0, pym_paths[0])
else:
	import sysconfig
	pym_paths = [
		os.path.join(sysconfig.get_path("purelib"), x) for x in ("_emerge", "portage")
	]
# Avoid sandbox violations after Python upgrade.
if os.environ.get("SANDBOX_ON") == "1":
	sandbox_write = os.environ.get("SANDBOX_WRITE", "").split(":")
	for pym_path in pym_paths:
		if pym_path not in sandbox_write:
			sandbox_write.append(pym_path)
			os.environ["SANDBOX_WRITE"] = ":".join(filter(None, sandbox_write))
	del pym_path, sandbox_write
del pym_paths

import portage
portage._internal_caller = True
portage._disable_legacy_globals()

from portage.util._eventloop.global_event_loop import global_event_loop
from _emerge.AbstractPollTask import AbstractPollTask
from _emerge.PipeReader import PipeReader

RETURNCODE_WRITE_FAILED = 2

class FifoWriter(AbstractPollTask):

	__slots__ = ('buf', 'fifo', '_fd')

	def _start(self):
		try:
			self._fd = os.open(self.fifo, os.O_WRONLY|os.O_NONBLOCK)
		except OSError as e:
			if e.errno == errno.ENXIO:
				# This happens if the daemon has been killed.
				self.returncode = RETURNCODE_WRITE_FAILED
				self._unregister()
				self._async_wait()
				return
			else:
				raise
		self.scheduler.add_writer(
			self._fd,
			self._output_handler)
		self._registered = True

	def _output_handler(self):
		# The whole buf should be able to fit in the fifo with
		# a single write call, so there's no valid reason for
		# os.write to raise EAGAIN here.
		fd = self._fd
		buf = self.buf
		while buf:
			try:
				buf = buf[os.write(fd, buf):]
			except EnvironmentError:
				self.returncode = RETURNCODE_WRITE_FAILED
				self._async_wait()
				return

		self.returncode = os.EX_OK
		self._async_wait()

	def _cancel(self):
		self.returncode = self._cancelled_returncode
		self._unregister()

	def _unregister(self):
		self._registered = False
		if self._fd is not None:
			self.scheduler.remove_writer(self._fd)
			os.close(self._fd)
			self._fd = None

class EbuildIpc:

	# Timeout for each individual communication attempt (we retry
	# as long as the daemon process appears to be alive).
	_COMMUNICATE_RETRY_TIMEOUT = 15 # seconds

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

	def _run_writer(self, fifo_writer, msg):
		"""
		Wait on pid and return an appropriate exit code. This
		may return unsuccessfully due to timeout if the daemon
		process does not appear to be alive.
		"""

		start_time = time.time()

		fifo_writer.start()
		eof = fifo_writer.poll() is not None

		while not eof:
			fifo_writer._wait_loop(timeout=self._COMMUNICATE_RETRY_TIMEOUT)

			eof = fifo_writer.poll() is not None
			if eof:
				break
			elif self._daemon_is_alive():
				self._timeout_retry_msg(start_time, msg)
			else:
				fifo_writer.cancel()
				self._no_daemon_msg()
				fifo_writer.wait()
				return 2

		return fifo_writer.wait()

	def _receive_reply(self, input_fd):

		start_time = time.time()

		pipe_reader = PipeReader(input_files={"input_fd":input_fd},
			scheduler=global_event_loop())
		pipe_reader.start()

		eof = pipe_reader.poll() is not None

		while not eof:
			pipe_reader._wait_loop(timeout=self._COMMUNICATE_RETRY_TIMEOUT)
			eof = pipe_reader.poll() is not None
			if not eof:
				if self._daemon_is_alive():
					self._timeout_retry_msg(start_time,
						portage.localization._('during read'))
				else:
					pipe_reader.cancel()
					self._no_daemon_msg()
					return 2

		buf = pipe_reader.getvalue()

		retval = 2

		if not buf:

			portage.util.writemsg_level(
				"ebuild-ipc: %s\n" % \
				(portage.localization._('read failed'),),
				level=logging.ERROR, noiselevel=-1)

		else:

			try:
				reply = pickle.loads(buf)
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

		# Open the input fifo before the output fifo, in order to make it
		# possible for the daemon to send a reply without blocking. This
		# improves performance, and also makes it possible for the daemon
		# to do a non-blocking write without a race condition.
		input_fd = os.open(self.ipc_out_fifo,
			os.O_RDONLY|os.O_NONBLOCK)

		# Use forks so that the child process can handle blocking IO
		# un-interrupted, while the parent handles all timeout
		# considerations. This helps to avoid possible race conditions
		# from interference between timeouts and blocking IO operations.
		msg = portage.localization._('during write')
		retval = self._run_writer(FifoWriter(buf=pickle.dumps(args),
			fifo=self.ipc_in_fifo, scheduler=global_event_loop()), msg)

		if retval != os.EX_OK:
			portage.util.writemsg_level(
				"ebuild-ipc: %s: %s\n" % (msg,
				portage.localization._('subprocess failure: %s') % \
				retval), level=logging.ERROR, noiselevel=-1)
			return retval

		if not self._daemon_is_alive():
			self._no_daemon_msg()
			return 2

		return self._receive_reply(input_fd)

def ebuild_ipc_main(args):
	ebuild_ipc = EbuildIpc()
	return ebuild_ipc.communicate(args)

if __name__ == '__main__':
	try:
		sys.exit(ebuild_ipc_main(sys.argv[1:]))
	finally:
		global_event_loop().close()
