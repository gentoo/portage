# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['get_cpu_count']


def get_cpu_count():
	"""
	Try to obtain the number of CPUs available.

	@return: Number of CPUs or None if unable to obtain.
	"""

	try:
		import multiprocessing
		return multiprocessing.cpu_count()
	except (ImportError, NotImplementedError):
		return None
