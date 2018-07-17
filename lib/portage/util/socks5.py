# SOCKSv5 proxy manager for network-sandbox
# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os
import signal

from portage import _python_interpreter
from portage.data import portage_gid, portage_uid, userpriv_groups
from portage.process import atexit_register, spawn


class ProxyManager(object):
	"""
	A class to start and control a single running SOCKSv5 server process
	for Portage.
	"""

	def __init__(self):
		self.socket_path = None
		self._pids = []

	def start(self, settings):
		"""
		Start the SOCKSv5 server.

		@param settings: Portage settings instance (used to determine
		paths)
		@type settings: portage.config
		"""
		try:
			import asyncio  # NOQA
		except ImportError:
			raise NotImplementedError('SOCKSv5 proxy requires asyncio module')

		self.socket_path = os.path.join(settings['PORTAGE_TMPDIR'],
				'.portage.%d.net.sock' % os.getpid())
		server_bin = os.path.join(settings['PORTAGE_BIN_PATH'], 'socks5-server.py')
		self._pids = spawn([_python_interpreter, server_bin, self.socket_path],
				returnpid=True, uid=portage_uid, gid=portage_gid,
				groups=userpriv_groups, umask=0o077)

	def stop(self):
		"""
		Stop the SOCKSv5 server.
		"""
		for p in self._pids:
			os.kill(p, signal.SIGINT)
			os.waitpid(p, 0)

		self.socket_path = None
		self._pids = []

	def is_running(self):
		"""
		Check whether the SOCKSv5 server is running.

		@return: True if the server is running, False otherwise
		"""
		return self.socket_path is not None


proxy = ProxyManager()


def get_socks5_proxy(settings):
	"""
	Get UNIX socket path for a SOCKSv5 proxy. A new proxy is started if
	one isn't running yet, and an atexit event is added to stop the proxy
	on exit.

	@param settings: Portage settings instance (used to determine paths)
	@type settings: portage.config
	@return: (string) UNIX socket path
	"""

	if not proxy.is_running():
		proxy.start(settings)
		atexit_register(proxy.stop)

	return proxy.socket_path
