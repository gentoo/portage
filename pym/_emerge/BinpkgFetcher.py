# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AsynchronousLock import AsynchronousLock
from _emerge.SpawnProcess import SpawnProcess
try:
	from urllib.parse import urlparse as urllib_parse_urlparse
except ImportError:
	from urlparse import urlparse as urllib_parse_urlparse
import stat
import sys
import portage
from portage import os
from portage.util._pty import _create_pty_or_pipe

if sys.hexversion >= 0x3000000:
	long = int

class BinpkgFetcher(SpawnProcess):

	__slots__ = ("pkg", "pretend",
		"locked", "pkg_path", "_lock_obj")

	def __init__(self, **kwargs):
		SpawnProcess.__init__(self, **kwargs)
		pkg = self.pkg
		self.pkg_path = pkg.root_config.trees["bintree"].getname(pkg.cpv)

	def _start(self):

		pkg = self.pkg
		pretend = self.pretend
		bintree = pkg.root_config.trees["bintree"]
		settings = bintree.settings
		use_locks = "distlocks" in settings.features
		pkg_path = self.pkg_path

		if not pretend:
			portage.util.ensure_dirs(os.path.dirname(pkg_path))
			if use_locks:
				self.lock()
		exists = os.path.exists(pkg_path)
		resume = exists and os.path.basename(pkg_path) in bintree.invalids
		if not (pretend or resume):
			# Remove existing file or broken symlink.
			try:
				os.unlink(pkg_path)
			except OSError:
				pass

		# urljoin doesn't work correctly with
		# unrecognized protocols like sftp
		if bintree._remote_has_index:
			rel_uri = bintree._remotepkgs[pkg.cpv].get("PATH")
			if not rel_uri:
				rel_uri = pkg.cpv + ".tbz2"
			remote_base_uri = bintree._remotepkgs[pkg.cpv]["BASE_URI"]
			uri = remote_base_uri.rstrip("/") + "/" + rel_uri.lstrip("/")
		else:
			uri = settings["PORTAGE_BINHOST"].rstrip("/") + \
				"/" + pkg.pf + ".tbz2"

		if pretend:
			portage.writemsg_stdout("\n%s\n" % uri, noiselevel=-1)
			self._set_returncode((self.pid, os.EX_OK << 8))
			self.wait()
			return

		protocol = urllib_parse_urlparse(uri)[0]
		fcmd_prefix = "FETCHCOMMAND"
		if resume:
			fcmd_prefix = "RESUMECOMMAND"
		fcmd = settings.get(fcmd_prefix + "_" + protocol.upper())
		if not fcmd:
			fcmd = settings.get(fcmd_prefix)

		fcmd_vars = {
			"DISTDIR" : os.path.dirname(pkg_path),
			"URI"     : uri,
			"FILE"    : os.path.basename(pkg_path)
		}

		fetch_env = dict(settings.items())
		fetch_args = [portage.util.varexpand(x, mydict=fcmd_vars) \
			for x in portage.util.shlex_split(fcmd)]

		if self.fd_pipes is None:
			self.fd_pipes = {}
		fd_pipes = self.fd_pipes

		# Redirect all output to stdout since some fetchers like
		# wget pollute stderr (if portage detects a problem then it
		# can send it's own message to stderr).
		fd_pipes.setdefault(0, sys.__stdin__.fileno())
		fd_pipes.setdefault(1, sys.__stdout__.fileno())
		fd_pipes.setdefault(2, sys.__stdout__.fileno())

		self.args = fetch_args
		self.env = fetch_env
		if settings.selinux_enabled():
			self._selinux_type = settings["PORTAGE_FETCH_T"]
		SpawnProcess._start(self)

	def _pipe(self, fd_pipes):
		"""When appropriate, use a pty so that fetcher progress bars,
		like wget has, will work properly."""
		if self.background or not sys.__stdout__.isatty():
			# When the output only goes to a log file,
			# there's no point in creating a pty.
			return os.pipe()
		stdout_pipe = None
		if not self.background:
			stdout_pipe = fd_pipes.get(1)
		got_pty, master_fd, slave_fd = \
			_create_pty_or_pipe(copy_term_size=stdout_pipe)
		return (master_fd, slave_fd)

	def _set_returncode(self, wait_retval):
		SpawnProcess._set_returncode(self, wait_retval)
		if not self.pretend and self.returncode == os.EX_OK:
			# If possible, update the mtime to match the remote package if
			# the fetcher didn't already do it automatically.
			bintree = self.pkg.root_config.trees["bintree"]
			if bintree._remote_has_index:
				remote_mtime = bintree._remotepkgs[self.pkg.cpv].get("MTIME")
				if remote_mtime is not None:
					try:
						remote_mtime = long(remote_mtime)
					except ValueError:
						pass
					else:
						try:
							local_mtime = os.stat(self.pkg_path)[stat.ST_MTIME]
						except OSError:
							pass
						else:
							if remote_mtime != local_mtime:
								try:
									os.utime(self.pkg_path,
										(remote_mtime, remote_mtime))
								except OSError:
									pass

		if self.locked:
			self.unlock()

	def lock(self):
		"""
		This raises an AlreadyLocked exception if lock() is called
		while a lock is already held. In order to avoid this, call
		unlock() or check whether the "locked" attribute is True
		or False before calling lock().
		"""
		if self._lock_obj is not None:
			raise self.AlreadyLocked((self._lock_obj,))

		async_lock = AsynchronousLock(path=self.pkg_path,
			scheduler=self.scheduler)
		async_lock.start()

		if async_lock.wait() != os.EX_OK:
			# TODO: Use CompositeTask for better handling, like in EbuildPhase.
			raise AssertionError("AsynchronousLock failed with returncode %s" \
				% (async_lock.returncode,))

		self._lock_obj = async_lock
		self.locked = True

	class AlreadyLocked(portage.exception.PortageException):
		pass

	def unlock(self):
		if self._lock_obj is None:
			return
		self._lock_obj.unlock()
		self._lock_obj = None
		self.locked = False

