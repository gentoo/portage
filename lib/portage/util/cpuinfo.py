# Copyright 2015-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ['get_cpu_count']

# Before you set out to change this function, figure out what you're really
# asking:
#
# - How many CPUs exist in this system (e.g. that the kernel is aware of?)
#   This is 'getconf _NPROCESSORS_CONF' / get_nprocs_conf(3)
#   In modern Linux, implemented by counting CPUs in /sys/devices/system/cpu/
#
# - How many CPUs in this system are ONLINE right now?
#   This is 'getconf _NPROCESSORS_ONLN' / get_nprocs(3)
#   In modern Linux, implemented by parsing /sys/devices/system/cpu/online
#
# - How many CPUs are available to this program?
#   This is 'nproc' / sched_getaffinity(2), which is implemented in modern
#   Linux kernels by querying the kernel scheduler; This might not be available
#   in some non-Linux systems!
#
# - How many CPUs are available to this thread?
#   This is pthread_getaffinity_np(3)
#
# As a further warning, the results returned by this function can differ
# between runs, if altered by the scheduler or other external factors.

def get_cpu_count():
	"""
	Try to obtain the number of CPUs available to this process.

	@return: Number of CPUs or None if unable to obtain.
	"""
	try:
		import os
		# This was introduced in Python 3.3 only, but exists in Linux
		# all the way back to the 2.5.8 kernel.
		# This NOT available in FreeBSD!
		return len(os.sched_getaffinity(0))
	except (ImportError, NotImplementedError, AttributeError):
		pass

	try:
		import multiprocessing
		return multiprocessing.cpu_count()
	except (ImportError, NotImplementedError):
		return None
