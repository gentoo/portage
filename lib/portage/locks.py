# portage: Lock management code
# Copyright 2004-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ["lockdir", "unlockdir", "lockfile", "unlockfile", \
	"hardlock_name", "hardlink_is_mine", "hardlink_lockfile", \
	"unhardlink_lockfile", "hardlock_cleanup"]

import errno
import fcntl
import functools
import multiprocessing
import sys
import tempfile
import time
import typing
import warnings

import portage
from portage import os, _encodings, _unicode_decode
from portage.exception import (DirectoryNotFound, FileNotFound,
	InvalidData, TryAgain, OperationNotPermitted, PermissionDenied,
	ReadOnlyFileSystem)
from portage.util import writemsg
from portage.util.install_mask import _raise_exc
from portage.localization import _


HARDLINK_FD = -2
_HARDLINK_POLL_LATENCY = 3 # seconds

# Used by emerge in order to disable the "waiting for lock" message
# so that it doesn't interfere with the status display.
_quiet = False


_lock_fn = None
_open_fds = {}
_open_inodes = {}

class _lock_manager:
	__slots__ = ('fd', 'inode_key')
	def __init__(self, fd, fstat_result, path):
		self.fd = fd
		self.inode_key = (fstat_result.st_dev, fstat_result.st_ino)
		if self.inode_key in _open_inodes:
			# This means that the lock is already held by the current
			# process, so the caller will have to try again. This case
			# is encountered with the default fcntl.lockf function, and
			# with the alternative fcntl.flock function TryAgain is
			# raised earlier.
			os.close(fd)
			raise TryAgain(path)
		_open_fds[fd] = self
		_open_inodes[self.inode_key] = self
	def close(self):
		os.close(self.fd)
		del _open_fds[self.fd]
		del _open_inodes[self.inode_key]


def _get_lock_fn():
	"""
	Returns fcntl.lockf if proven to work, and otherwise returns fcntl.flock.
	On some platforms fcntl.lockf is known to be broken.
	"""
	global _lock_fn
	if _lock_fn is not None:
		return _lock_fn

	if _test_lock_fn(
		lambda path, fd, flags: fcntl.lockf(fd, flags) and functools.partial(
			unlockfile, (path, fd, flags, fcntl.lockf)
		)
	):
		_lock_fn = fcntl.lockf
		return _lock_fn

	# Fall back to fcntl.flock.
	_lock_fn = fcntl.flock
	return _lock_fn


def _test_lock_fn(lock_fn: typing.Callable[[str, int, int], typing.Callable[[], None]]) -> bool:
	def _test_lock(fd, lock_path):
		os.close(fd)
		try:
			with open(lock_path, 'a') as f:
				lock_fn(lock_path, f.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)
		except (TryAgain, EnvironmentError) as e:
			if isinstance(e, TryAgain) or e.errno == errno.EAGAIN:
				# Parent process holds lock, as expected.
				sys.exit(0)


		# Something went wrong.
		sys.exit(1)

	fd, lock_path = tempfile.mkstemp()
	unlock_fn = None
	try:
		try:
			unlock_fn = lock_fn(lock_path, fd, fcntl.LOCK_EX)
		except (TryAgain, EnvironmentError):
			pass
		else:
			_lock_manager(fd, os.fstat(fd), lock_path)
			proc = multiprocessing.Process(target=_test_lock,
				args=(fd, lock_path))
			proc.start()
			proc.join()
			if proc.exitcode == os.EX_OK:
				# the test passed
				return True
	finally:
		try:
			os.unlink(lock_path)
		except OSError:
			pass
		if unlock_fn is not None:
			unlock_fn()
	return False


def _close_fds():
	"""
	This is intended to be called after a fork, in order to close file
	descriptors for locks held by the parent process. This can be called
	safely after a fork without exec, unlike the _setup_pipes close_fds
	behavior.
	"""
	for fd in list(_open_fds.values()):
		fd.close()

def lockdir(mydir, flags=0):
	return lockfile(mydir, wantnewlockfile=1, flags=flags)
def unlockdir(mylock):
	return unlockfile(mylock)

def lockfile(mypath, wantnewlockfile=0, unlinkfile=0,
	waiting_msg=None, flags=0):
	"""
	If wantnewlockfile is True then this creates a lockfile in the parent
	directory as the file: '.' + basename + '.portage_lockfile'.
	"""
	lock = None
	while lock is None:
		lock = _lockfile_iteration(mypath, wantnewlockfile=wantnewlockfile,
			unlinkfile=unlinkfile, waiting_msg=waiting_msg, flags=flags)
		if lock is None:
			writemsg(_("lockfile removed by previous lock holder, retrying\n"), 1)
	return lock


def _lockfile_iteration(mypath, wantnewlockfile=False, unlinkfile=False,
	waiting_msg=None, flags=0):
	"""
	Acquire a lock on mypath, without retry. Return None if the lockfile
	was removed by previous lock holder (caller must retry).

	@param mypath: lock file path
	@type mypath: str
	@param wantnewlockfile: use a separate new lock file
	@type wantnewlockfile: bool
	@param unlinkfile: remove lock file prior to unlock
	@type unlinkfile: bool
	@param waiting_msg: message to show before blocking
	@type waiting_msg: str
	@param flags: lock flags (only supports os.O_NONBLOCK)
	@type flags: int
	@rtype: bool
	@return: unlockfile tuple on success, None if retry is needed
	"""
	if not mypath:
		raise InvalidData(_("Empty path given"))

	# Since Python 3.4, chown requires int type (no proxies).
	portage_gid = int(portage.data.portage_gid)

	# Support for file object or integer file descriptor parameters is
	# deprecated due to ambiguity in whether or not it's safe to close
	# the file descriptor, making it prone to "Bad file descriptor" errors
	# or file descriptor leaks.
	if isinstance(mypath, str) and mypath[-1] == '/':
		mypath = mypath[:-1]

	lockfilename_path = mypath
	if hasattr(mypath, 'fileno'):
		warnings.warn("portage.locks.lockfile() support for "
			"file object parameters is deprecated. Use a file path instead.",
			DeprecationWarning, stacklevel=2)
		lockfilename_path = getattr(mypath, 'name', None)
		mypath = mypath.fileno()
	if isinstance(mypath, int):
		warnings.warn("portage.locks.lockfile() support for integer file "
			"descriptor parameters is deprecated. Use a file path instead.",
			DeprecationWarning, stacklevel=2)
		lockfilename    = mypath
		wantnewlockfile = 0
		unlinkfile      = 0
	elif wantnewlockfile:
		base, tail = os.path.split(mypath)
		lockfilename = os.path.join(base, "." + tail + ".portage_lockfile")
		lockfilename_path = lockfilename
		unlinkfile   = 1
	else:
		lockfilename = mypath

	if isinstance(mypath, str):
		if not os.path.exists(os.path.dirname(mypath)):
			raise DirectoryNotFound(os.path.dirname(mypath))
		preexisting = os.path.exists(lockfilename)
		old_mask = os.umask(000)
		try:
			while True:
				try:
					myfd = os.open(lockfilename, os.O_CREAT|os.O_RDWR, 0o660)
				except OSError as e:
					if e.errno in (errno.ENOENT, errno.ESTALE) and os.path.isdir(os.path.dirname(lockfilename)):
						# Retry required for NFS (see bug 636798).
						continue
					else:
						_raise_exc(e)
				else:
					break

			if not preexisting:
				try:
					if portage.data.secpass >= 1 and os.stat(lockfilename).st_gid != portage_gid:
						os.chown(lockfilename, -1, portage_gid)
				except OSError as e:
					if e.errno in (errno.ENOENT, errno.ESTALE):
						os.close(myfd)
						return None
					writemsg("%s: chown('%s', -1, %d)\n" % \
						(e, lockfilename, portage_gid), noiselevel=-1)
					writemsg(_("Cannot chown a lockfile: '%s'\n") % \
						lockfilename, noiselevel=-1)
					writemsg(_("Group IDs of current user: %s\n") % \
						" ".join(str(n) for n in os.getgroups()),
						noiselevel=-1)
		finally:
			os.umask(old_mask)

	elif isinstance(mypath, int):
		myfd = mypath

	else:
		raise ValueError(_("Unknown type passed in '%s': '%s'") % \
			(type(mypath), mypath))

	# try for a non-blocking lock, if it's held, throw a message
	# we're waiting on lockfile and use a blocking attempt.
	locking_method = portage._eintr_func_wrapper(_get_lock_fn())
	try:
		if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
			raise IOError(errno.ENOSYS, "Function not implemented")
		locking_method(myfd, fcntl.LOCK_EX|fcntl.LOCK_NB)
	except IOError as e:
		if not hasattr(e, "errno"):
			raise
		if e.errno in (errno.EACCES, errno.EAGAIN, errno.ENOLCK):
			# resource temp unavailable; eg, someone beat us to the lock.
			if flags & os.O_NONBLOCK:
				os.close(myfd)
				raise TryAgain(mypath)

			global _quiet
			if _quiet:
				out = None
			else:
				out = portage.output.EOutput()
			if waiting_msg is None:
				if isinstance(mypath, int):
					waiting_msg = _("waiting for lock on fd %i") % myfd
				else:
					waiting_msg = _("waiting for lock on %s") % lockfilename
			if out is not None:
				out.ebegin(waiting_msg)
			# try for the exclusive lock now.
			enolock_msg_shown = False
			while True:
				try:
					locking_method(myfd, fcntl.LOCK_EX)
				except EnvironmentError as e:
					if e.errno == errno.ENOLCK:
						# This is known to occur on Solaris NFS (see
						# bug #462694). Assume that the error is due
						# to temporary exhaustion of record locks,
						# and loop until one becomes available.
						if not enolock_msg_shown:
							enolock_msg_shown = True
							if isinstance(mypath, int):
								context_desc = _("Error while waiting "
									"to lock fd %i") % myfd
							else:
								context_desc = _("Error while waiting "
									"to lock '%s'") % lockfilename
							writemsg("\n!!! %s: %s\n" % (context_desc, e),
								noiselevel=-1)

						time.sleep(_HARDLINK_POLL_LATENCY)
						continue

					if out is not None:
						out.eend(1, str(e))
					raise
				else:
					break

			if out is not None:
				out.eend(os.EX_OK)
		elif e.errno in (errno.ENOSYS,):
			# We're not allowed to lock on this FS.
			if not isinstance(lockfilename, int):
				# If a file object was passed in, it's not safe
				# to close the file descriptor because it may
				# still be in use.
				os.close(myfd)
			lockfilename_path = _unicode_decode(lockfilename_path,
				encoding=_encodings['fs'], errors='strict')
			if not isinstance(lockfilename_path, str):
				raise
			link_success = hardlink_lockfile(lockfilename_path,
				waiting_msg=waiting_msg, flags=flags)
			if not link_success:
				raise
			lockfilename = lockfilename_path
			locking_method = None
			myfd = HARDLINK_FD
		else:
			raise

	fstat_result = None
	if isinstance(lockfilename, str) and myfd != HARDLINK_FD and unlinkfile:
		try:
			(removed, fstat_result) = _lockfile_was_removed(myfd, lockfilename)
		except Exception:
			# Do not leak the file descriptor here.
			os.close(myfd)
			raise
		else:
			if removed:
				# Removed by previous lock holder... Caller will retry...
				os.close(myfd)
				return None

	if myfd != HARDLINK_FD:
		_lock_manager(myfd, os.fstat(myfd) if fstat_result is None else fstat_result, mypath)

	writemsg(str((lockfilename, myfd, unlinkfile)) + "\n", 1)
	return (lockfilename, myfd, unlinkfile, locking_method)


def _lockfile_was_removed(lock_fd, lock_path):
	"""
	Check if lock_fd still refers to a file located at lock_path, since
	the file may have been removed by a concurrent process that held the
	lock earlier. This implementation includes support for NFS, where
	stat is not reliable for removed files due to the default file
	attribute cache behavior ('ac' mount option).

	@param lock_fd: an open file descriptor for a lock file
	@type lock_fd: int
	@param lock_path: path of lock file
	@type lock_path: str
	@rtype: bool
	@return: a tuple of (removed, fstat_result), where removed is True if
		lock_path does not correspond to lock_fd, and False otherwise
	"""
	try:
		fstat_st = os.fstat(lock_fd)
	except OSError as e:
		if e.errno not in (errno.ENOENT, errno.ESTALE):
			_raise_exc(e)
		return (True, None)

	# Since stat is not reliable for removed files on NFS with the default
	# file attribute cache behavior ('ac' mount option), create a temporary
	# hardlink in order to prove that the file path exists on the NFS server.
	hardlink_path = hardlock_name(lock_path)
	try:
		os.unlink(hardlink_path)
	except OSError as e:
		if e.errno not in (errno.ENOENT, errno.ESTALE):
			_raise_exc(e)
	try:
		try:
			os.link(lock_path, hardlink_path)
		except OSError as e:
			if e.errno not in (errno.ENOENT, errno.ESTALE):
				_raise_exc(e)
			return (True, None)

		hardlink_stat = os.stat(hardlink_path)
		if hardlink_stat.st_ino != fstat_st.st_ino or hardlink_stat.st_dev != fstat_st.st_dev:
			# Create another hardlink in order to detect whether or not
			# hardlink inode numbers are expected to match. For example,
			# inode numbers are not expected to match for sshfs.
			inode_test = hardlink_path + '-inode-test'
			try:
				os.unlink(inode_test)
			except OSError as e:
				if e.errno not in (errno.ENOENT, errno.ESTALE):
					_raise_exc(e)
			try:
				os.link(hardlink_path, inode_test)
			except OSError as e:
				if e.errno not in (errno.ENOENT, errno.ESTALE):
					_raise_exc(e)
				return (True, None)
			else:
				if not os.path.samefile(hardlink_path, inode_test):
					# This implies that inode numbers are not expected
					# to match for this file system, so use a simple
					# stat call to detect if lock_path has been removed.
					return (not os.path.exists(lock_path), fstat_st)
			finally:
				try:
					os.unlink(inode_test)
				except OSError as e:
					if e.errno not in (errno.ENOENT, errno.ESTALE):
						_raise_exc(e)
			return (True, None)
	finally:
		try:
			os.unlink(hardlink_path)
		except OSError as e:
			if e.errno not in (errno.ENOENT, errno.ESTALE):
				_raise_exc(e)
	return (False, fstat_st)


def _fstat_nlink(fd):
	"""
	@param fd: an open file descriptor
	@type fd: Integer
	@rtype: Integer
	@return: the current number of hardlinks to the file
	"""
	try:
		return os.fstat(fd).st_nlink
	except EnvironmentError as e:
		if e.errno in (errno.ENOENT, errno.ESTALE):
			# Some filesystems such as CIFS return
			# ENOENT which means st_nlink == 0.
			return 0
		raise

def unlockfile(mytuple):

	#XXX: Compatability hack.
	if len(mytuple) == 3:
		lockfilename, myfd, unlinkfile = mytuple
		locking_method = fcntl.flock
	elif len(mytuple) == 4:
		lockfilename, myfd, unlinkfile, locking_method = mytuple
	else:
		raise InvalidData

	if myfd == HARDLINK_FD:
		unhardlink_lockfile(lockfilename, unlinkfile=unlinkfile)
		return True

	# myfd may be None here due to myfd = mypath in lockfile()
	if isinstance(lockfilename, str) and \
		not os.path.exists(lockfilename):
		writemsg(_("lockfile does not exist '%s'\n") % lockfilename, 1)
		if myfd is not None:
			_open_fds[myfd].close()
		return False

	try:
		if myfd is None:
			myfd = os.open(lockfilename, os.O_WRONLY, 0o660)
			unlinkfile = 1
		locking_method(myfd, fcntl.LOCK_UN)
	except OSError:
		if isinstance(lockfilename, str):
			_open_fds[myfd].close()
		raise IOError(_("Failed to unlock file '%s'\n") % lockfilename)

	try:
		# This sleep call was added to allow other processes that are
		# waiting for a lock to be able to grab it before it is deleted.
		# lockfile() already accounts for this situation, however, and
		# the sleep here adds more time than is saved overall, so am
		# commenting until it is proved necessary.
		#time.sleep(0.0001)
		if unlinkfile:
			locking_method(myfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
			# We won the lock, so there isn't competition for it.
			# We can safely delete the file.
			writemsg(_("Got the lockfile...\n"), 1)
			if _fstat_nlink(myfd) == 1:
				os.unlink(lockfilename)
				writemsg(_("Unlinked lockfile...\n"), 1)
				locking_method(myfd, fcntl.LOCK_UN)
			else:
				writemsg(_("lockfile does not exist '%s'\n") % lockfilename, 1)
				_open_fds[myfd].close()
				return False
	except SystemExit:
		raise
	except Exception as e:
		writemsg(_("Failed to get lock... someone took it.\n"), 1)
		writemsg(str(e) + "\n", 1)

	# why test lockfilename?  because we may have been handed an
	# fd originally, and the caller might not like having their
	# open fd closed automatically on them.
	if isinstance(lockfilename, str):
		_open_fds[myfd].close()

	return True


def hardlock_name(path):
	base, tail = os.path.split(path)
	return os.path.join(base, ".%s.hardlock-%s-%s" %
		(tail, portage._decode_argv([os.uname()[1]])[0], portage.getpid()))

def hardlink_is_mine(link, lock):
	try:
		lock_st = os.stat(lock)
		if lock_st.st_nlink == 2:
			link_st = os.stat(link)
			return lock_st.st_ino == link_st.st_ino and \
				lock_st.st_dev == link_st.st_dev
	except OSError:
		pass
	return False

def hardlink_lockfile(lockfilename, max_wait=DeprecationWarning,
	waiting_msg=None, flags=0):
	"""Does the NFS, hardlink shuffle to ensure locking on the disk.
	We create a PRIVATE hardlink to the real lockfile, that is just a
	placeholder on the disk.
	If our file can 2 references, then we have the lock. :)
	Otherwise we lather, rise, and repeat.
	"""

	if max_wait is not DeprecationWarning:
		warnings.warn("The 'max_wait' parameter of "
			"portage.locks.hardlink_lockfile() is now unused. Use "
			"flags=os.O_NONBLOCK instead.",
			DeprecationWarning, stacklevel=2)

	global _quiet
	out = None
	displayed_waiting_msg = False
	preexisting = os.path.exists(lockfilename)
	myhardlock = hardlock_name(lockfilename)

	# Since Python 3.4, chown requires int type (no proxies).
	portage_gid = int(portage.data.portage_gid)

	# myhardlock must not exist prior to our link() call, and we can
	# safely unlink it since its file name is unique to our PID
	try:
		os.unlink(myhardlock)
	except OSError as e:
		if e.errno in (errno.ENOENT, errno.ESTALE):
			pass
		else:
			func_call = "unlink('%s')" % myhardlock
			if e.errno == OperationNotPermitted.errno:
				raise OperationNotPermitted(func_call)
			elif e.errno == PermissionDenied.errno:
				raise PermissionDenied(func_call)
			else:
				raise

	while True:
		# create lockfilename if it doesn't exist yet
		try:
			myfd = os.open(lockfilename, os.O_CREAT|os.O_RDWR, 0o660)
		except OSError as e:
			func_call = "open('%s')" % lockfilename
			if e.errno == OperationNotPermitted.errno:
				raise OperationNotPermitted(func_call)
			elif e.errno == PermissionDenied.errno:
				raise PermissionDenied(func_call)
			elif e.errno == ReadOnlyFileSystem.errno:
				raise ReadOnlyFileSystem(func_call)
			else:
				raise
		else:
			myfd_st = None
			try:
				myfd_st = os.fstat(myfd)
				if not preexisting:
					# Don't chown the file if it is preexisting, since we
					# want to preserve existing permissions in that case.
					if portage.data.secpass >= 1 and myfd_st.st_gid != portage_gid:
						os.fchown(myfd, -1, portage_gid)
			except OSError as e:
				if e.errno not in (errno.ENOENT, errno.ESTALE):
					writemsg("%s: fchown('%s', -1, %d)\n" % \
						(e, lockfilename, portage_gid), noiselevel=-1)
					writemsg(_("Cannot chown a lockfile: '%s'\n") % \
						lockfilename, noiselevel=-1)
					writemsg(_("Group IDs of current user: %s\n") % \
						" ".join(str(n) for n in os.getgroups()),
						noiselevel=-1)
				else:
					# another process has removed the file, so we'll have
					# to create it again
					continue
			finally:
				os.close(myfd)

			# If fstat shows more than one hardlink, then it's extremely
			# unlikely that the following link call will result in a lock,
			# so optimize away the wasteful link call and sleep or raise
			# TryAgain.
			if myfd_st is not None and myfd_st.st_nlink < 2:
				try:
					os.link(lockfilename, myhardlock)
				except OSError as e:
					func_call = "link('%s', '%s')" % (lockfilename, myhardlock)
					if e.errno == OperationNotPermitted.errno:
						raise OperationNotPermitted(func_call)
					elif e.errno == PermissionDenied.errno:
						raise PermissionDenied(func_call)
					elif e.errno in (errno.ESTALE, errno.ENOENT):
						# another process has removed the file, so we'll have
						# to create it again
						continue
					else:
						raise
				else:
					if hardlink_is_mine(myhardlock, lockfilename):
						if out is not None:
							out.eend(os.EX_OK)
						break

					try:
						os.unlink(myhardlock)
					except OSError as e:
						# This should not happen, since the file name of
						# myhardlock is unique to our host and PID,
						# and the above link() call succeeded.
						if e.errno not in (errno.ENOENT, errno.ESTALE):
							raise
						raise FileNotFound(myhardlock)

		if flags & os.O_NONBLOCK:
			raise TryAgain(lockfilename)

		if out is None and not _quiet:
			out = portage.output.EOutput()
		if out is not None and not displayed_waiting_msg:
			displayed_waiting_msg = True
			if waiting_msg is None:
				waiting_msg = _("waiting for lock on %s\n") % lockfilename
			out.ebegin(waiting_msg)

		time.sleep(_HARDLINK_POLL_LATENCY)

	return True

def unhardlink_lockfile(lockfilename, unlinkfile=True):
	myhardlock = hardlock_name(lockfilename)
	if unlinkfile and hardlink_is_mine(myhardlock, lockfilename):
		# Make sure not to touch lockfilename unless we really have a lock.
		try:
			os.unlink(lockfilename)
		except OSError:
			pass
	try:
		os.unlink(myhardlock)
	except OSError:
		pass

def hardlock_cleanup(path, remove_all_locks=False):
	myhost = portage._decode_argv([os.uname()[1]])[0]
	mydl = os.listdir(path)

	results = []
	mycount = 0

	mylist = {}
	for x in mydl:
		if os.path.isfile(path + "/" + x):
			parts = x.split(".hardlock-")
			if len(parts) == 2:
				filename = parts[0][1:]
				hostpid  = parts[1].split("-")
				host  = "-".join(hostpid[:-1])
				pid   = hostpid[-1]

				if filename not in mylist:
					mylist[filename] = {}
				if host not in mylist[filename]:
					mylist[filename][host] = []
				mylist[filename][host].append(pid)

				mycount += 1


	results.append(_("Found %(count)s locks") % {"count": mycount})

	for x in mylist:
		if myhost in mylist[x] or remove_all_locks:
			mylockname = hardlock_name(path + "/" + x)
			if hardlink_is_mine(mylockname, path + "/" + x) or \
			   not os.path.exists(path + "/" + x) or \
				 remove_all_locks:
				for y in mylist[x]:
					for z in mylist[x][y]:
						filename = path + "/." + x + ".hardlock-" + y + "-" + z
						if filename == mylockname:
							continue
						try:
							# We're sweeping through, unlinking everyone's locks.
							os.unlink(filename)
							results.append(_("Unlinked: ") + filename)
						except OSError:
							pass
				try:
					os.unlink(path + "/" + x)
					results.append(_("Unlinked: ") + path + "/" + x)
					os.unlink(mylockname)
					results.append(_("Unlinked: ") + mylockname)
				except OSError:
					pass
			else:
				try:
					os.unlink(mylockname)
					results.append(_("Unlinked: ") + mylockname)
				except OSError:
					pass

	return results
