#!/usr/bin/python
# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#
# This is a helper which ebuild processes can use
# to communicate with portage's main python process.

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

	_COMMUNICATE_TIMEOUT_SECONDS = 40

	def __init__(self):
		self.fifo_dir = os.environ['PORTAGE_BUILDDIR']
		self.ipc_in_fifo = os.path.join(self.fifo_dir, '.ipc_in')
		self.ipc_out_fifo = os.path.join(self.fifo_dir, '.ipc_out')
		self.ipc_lock_file = os.path.join(self.fifo_dir, '.ipc_lock')

	def communicate(self, args):

		# Make locks quiet since unintended locking messages displayed on
		# stdout could corrupt the intended output of this program.
		portage.locks._quiet = True
		lock_obj = portage.locks.lockfile(self.ipc_lock_file, unlinkfile=True)
		start_time = time.time()

		try:
			try:
				portage.exception.AlarmSignal.register(
					self._COMMUNICATE_TIMEOUT_SECONDS)
				returncode = self._communicate(args)
				return returncode
			finally:
				portage.exception.AlarmSignal.unregister()
				portage.locks.unlockfile(lock_obj)
		except portage.exception.AlarmSignal:
			time_elapsed = time.time() - start_time
			portage.util.writemsg_level(
				('ebuild-ipc timed out after %d seconds\n') % \
				(time_elapsed,),
				level=logging.ERROR, noiselevel=-1)
			return 1

	def _communicate(self, args):
		input_fd = os.open(self.ipc_out_fifo, os.O_RDONLY|os.O_NONBLOCK)

		# File streams are in unbuffered mode since we do atomic
		# read and write of whole pickles.
		input_file = os.fdopen(input_fd, 'rb', 0)
		output_file = open(self.ipc_in_fifo, 'wb', 0)

		# Write the whole pickle in a single atomic write() call,
		# since the reader is in non-blocking mode and we want
		# it to get the whole pickle at once.
		output_file.write(pickle.dumps(args))
		output_file.flush()

		events = select.select([input_file], [], [])

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

		pickle_str = input_file.read()
		reply = pickle.loads(pickle_str)
		output_file.close()
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
