# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
import platform

getloadavg = getattr(os, "getloadavg", None)
if getloadavg is None:
	def getloadavg():
		"""
		Uses /proc/loadavg to emulate os.getloadavg().
		Raises OSError if the load average was unobtainable.
		"""
		try:
			if platform.system() in ["AIX", "HP-UX"]:
				loadavg_str = os.popen('LANG=C /usr/bin/uptime 2>/dev/null').readline().split()
				while loadavg_str[0] != 'load' and loadavg_str[1] != 'average:':
				    loadavg_str = loadavg_str[1:]
				loadavg_str = loadavg_str[2:5]
				loadavg_str = [x.rstrip(',') for x in loadavg_str]
				loadavg_str = ' '.join(loadavg_str)
			else:
				with open('/proc/loadavg') as f:
					loadavg_str = f.readline()
		except (IOError, IndexError):
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
