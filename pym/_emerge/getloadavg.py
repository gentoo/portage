# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os

getloadavg = getattr(os, "getloadavg", None)
if getloadavg is None:
	def getloadavg():
		"""
		Uses /proc/loadavg to emulate os.getloadavg().
		Raises OSError if the load average was unobtainable.
		"""
		try:
			with open('/proc/loadavg') as f:
				loadavg_str = f.readline()
		except IOError:
			# getloadavg() is only supposed to raise OSError, so convert
			raise OSError('unknown')
		loadavg_split = loadavg_str.split()
		if len(loadavg_split) < 3:
			raise OSError('unknown')
		loadavg_floats = []
		for i in range(3):
			try:
				loadavg_floats.append(float(loadavg_split[i]))
			except ValueError:
				raise OSError('unknown')
		return tuple(loadavg_floats)
