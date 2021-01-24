# SOCKSv5 proxy manager for network-sandbox
# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import os
import signal
import socket

import portage.data
from portage import _python_interpreter
from portage.data import portage_gid, portage_uid, userpriv_groups
from portage.process import atexit_register, spawn
from portage.util.futures import asyncio

class ProxyManager:
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

		tmpdir = os.path.join(settings['PORTAGE_TMPDIR'], 'portage')
		ensure_dirs_kwargs = {}
		if portage.secpass >= 1:
			ensure_dirs_kwargs['gid'] = portage_gid
			ensure_dirs_kwargs['mode'] = 0o70
			ensure_dirs_kwargs['mask'] = 0
		portage.util.ensure_dirs(tmpdir, **ensure_dirs_kwargs)

		self.socket_path = os.path.join(tmpdir,
				'.portage.%d.net.sock' % portage.getpid())
		server_bin = os.path.join(settings['PORTAGE_BIN_PATH'], 'socks5-server.py')
		spawn_kwargs = {}
		# The portage_uid check solves EPERM failures in Travis CI.
		if portage.data.secpass > 1 and os.geteuid() != portage_uid:
			spawn_kwargs.update(
				uid=portage_uid,
				gid=portage_gid,
				groups=userpriv_groups,
				umask=0o077)
		self._pids = spawn([_python_interpreter, server_bin, self.socket_path],
				returnpid=True, **spawn_kwargs)

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

	async def ready(self):
		"""
		Wait for the proxy socket to become ready. This method is a coroutine.
		"""

		while True:
			try:
				wait_retval = os.waitpid(self._pids[0], os.WNOHANG)
			except OSError as e:
				if e.errno == errno.EINTR:
					continue
				raise

			if wait_retval is not None and wait_retval != (0, 0):
				raise OSError(3, 'No such process')

			try:
				s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
				s.connect(self.socket_path)
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
				await asyncio.sleep(0.2)
			else:
				break
			finally:
				s.close()


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
