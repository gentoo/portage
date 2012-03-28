# portage: Lock management code
# Copyright 2004-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ["lockdir", "unlockdir", "lockfile", "unlockfile", \
	"hardlock_name", "hardlink_is_mine", "hardlink_lockfile", \
	"unhardlink_lockfile", "hardlock_cleanup"]

import errno
import fcntl
import platform
import sys
import time
import warnings

import portage
from portage import os, _encodings, _unicode_decode
from portage.exception import DirectoryNotFound, FileNotFound, \
	InvalidData, TryAgain, OperationNotPermitted, PermissionDenied
from portage.data import portage_gid
from portage.util import writemsg
from portage.localization import _

if sys.hexversion >= 0x3000000:
	basestring = str

HARDLINK_FD = -2
_HARDLINK_POLL_LATENCY = 3 # seconds
_default_lock_fn = fcntl.lockf

if platform.python_implementation() == 'PyPy':
	# workaround for https://bugs.pypy.org/issue747
	_default_lock_fn = fcntl.flock

# Used by emerge in order to disable the "waiting for lock" message
# so that it doesn't interfere with the status display.
_quiet = False


_open_fds = set()

def _close_fds():
	"""
	This is intended to be called after a fork, in order to close file
	descriptors for locks held by the parent process. This can be called
	safely after a fork without exec, unlike the _setup_pipes close_fds
	behavior.
	"""
	while _open_fds:
		os.close(_open_fds.pop())

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

	if not mypath:
		raise InvalidData(_("Empty path given"))

	# Support for file object or integer file descriptor parameters is
	# deprecated due to ambiguity in whether or not it's safe to close
	# the file descriptor, making it prone to "Bad file descriptor" errors
	# or file descriptor leaks.
	if isinstance(mypath, basestring) and mypath[-1] == '/':
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

	if isinstance(mypath, basestring):
		if not os.path.exists(os.path.dirname(mypath)):
			raise DirectoryNotFound(os.path.dirname(mypath))
		preexisting = os.path.exists(lockfilename)
		old_mask = os.umask(000)
		try:
			try:
				myfd = os.open(lockfilename, os.O_CREAT|os.O_RDWR, 0o660)
			except OSError as e:
				func_call = "open('%s')" % lockfilename
				if e.errno == OperationNotPermitted.errno:
					raise OperationNotPermitted(func_call)
				elif e.errno == PermissionDenied.errno:
					raise PermissionDenied(func_call)
				else:
					raise

			if not preexisting:
				try:
					if os.stat(lockfilename).st_gid != portage_gid:
						os.chown(lockfilename, -1, portage_gid)
				except OSError as e:
					if e.errno in (errno.ENOENT, errno.ESTALE):
						return lockfile(mypath,
							wantnewlockfile=wantnewlockfile,
							unlinkfile=unlinkfile, waiting_msg=waiting_msg,
							flags=flags)
					else:
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
	locking_method = _default_lock_fn
	try:
		if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
			raise IOError(errno.ENOSYS, "Function not implemented")
		locking_method(myfd, fcntl.LOCK_EX|fcntl.LOCK_NB)
	except IOError as e:
		if not hasattr(e, "errno"):
			raise
		if e.errno in (errno.EACCES, errno.EAGAIN):
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
					waiting_msg = _("waiting for lock on %s\n") % lockfilename
			if out is not None:
				out.ebegin(waiting_msg)
			# try for the exclusive lock now.
			try:
				locking_method(myfd, fcntl.LOCK_EX)
			except EnvironmentError as e:
				if out is not None:
					out.eend(1, str(e))
				raise
			if out is not None:
				out.eend(os.EX_OK)
		elif e.errno in (errno.ENOSYS, errno.ENOLCK):
			# We're not allowed to lock on this FS.
			if not isinstance(lockfilename, int):
				# If a file object was passed in, it's not safe
				# to close the file descriptor because it may
				# still be in use.
				os.close(myfd)
			lockfilename_path = _unicode_decode(lockfilename_path,
				encoding=_encodings['fs'], errors='strict')
			if not isinstance(lockfilename_path, basestring):
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

		
	if isinstance(lockfilename, basestring) and \
		myfd != HARDLINK_FD and _fstat_nlink(myfd) == 0:
		# The file was deleted on us... Keep trying to make one...
		os.close(myfd)
		writemsg(_("lockfile recurse\n"), 1)
		lockfilename, myfd, unlinkfile, locking_method = lockfile(
			mypath, wantnewlockfile=wantnewlockfile, unlinkfile=unlinkfile,
			waiting_msg=waiting_msg, flags=flags)

	if myfd != HARDLINK_FD:
		_open_fds.add(myfd)

	writemsg(str((lockfilename,myfd,unlinkfile))+"\n",1)
	return (lockfilename,myfd,unlinkfile,locking_method)

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
		lockfilename,myfd,unlinkfile = mytuple
		locking_method = fcntl.flock
	elif len(mytuple) == 4:
		lockfilename,myfd,unlinkfile,locking_method = mytuple
	else:
		raise InvalidData

	if(myfd == HARDLINK_FD):
		unhardlink_lockfile(lockfilename, unlinkfile=unlinkfile)
		return True
	
	# myfd may be None here due to myfd = mypath in lockfile()
	if isinstance(lockfilename, basestring) and \
		not os.path.exists(lockfilename):
		writemsg(_("lockfile does not exist '%s'\n") % lockfilename,1)
		if myfd is not None:
			os.close(myfd)
			_open_fds.remove(myfd)
		return False

	try:
		if myfd is None:
			myfd = os.open(lockfilename, os.O_WRONLY,0o660)
			unlinkfile = 1
		locking_method(myfd,fcntl.LOCK_UN)
	except OSError:
		if isinstance(lockfilename, basestring):
			os.close(myfd)
			_open_fds.remove(myfd)
		raise IOError(_("Failed to unlock file '%s'\n") % lockfilename)

	try:
		# This sleep call was added to allow other processes that are
		# waiting for a lock to be able to grab it before it is deleted.
		# lockfile() already accounts for this situation, however, and
		# the sleep here adds more time than is saved overall, so am
		# commenting until it is proved necessary.
		#time.sleep(0.0001)
		if unlinkfile:
			locking_method(myfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
			# We won the lock, so there isn't competition for it.
			# We can safely delete the file.
			writemsg(_("Got the lockfile...\n"), 1)
			if _fstat_nlink(myfd) == 1:
				os.unlink(lockfilename)
				writemsg(_("Unlinked lockfile...\n"), 1)
				locking_method(myfd,fcntl.LOCK_UN)
			else:
				writemsg(_("lockfile does not exist '%s'\n") % lockfilename, 1)
				os.close(myfd)
				_open_fds.remove(myfd)
				return False
	except SystemExit:
		raise
	except Exception as e:
		writemsg(_("Failed to get lock... someone took it.\n"), 1)
		writemsg(str(e)+"\n",1)

	# why test lockfilename?  because we may have been handed an
	# fd originally, and the caller might not like having their
	# open fd closed automatically on them.
	if isinstance(lockfilename, basestring):
		os.close(myfd)
		_open_fds.remove(myfd)

	return True




def hardlock_name(path):
	base, tail = os.path.split(path)
	return os.path.join(base, ".%s.hardlock-%s-%s" %
		(tail, os.uname()[1], os.getpid()))

def hardlink_is_mine(link,lock):
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
			else:
				raise
		else:
			myfd_st = None
			try:
				myfd_st = os.fstat(myfd)
				if not preexisting:
					# Don't chown the file if it is preexisting, since we
					# want to preserve existing permissions in that case.
					if myfd_st.st_gid != portage_gid:
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
	mypid  = str(os.getpid())
	myhost = os.uname()[1]
	mydl = os.listdir(path)

	results = []
	mycount = 0

	mylist = {}
	for x in mydl:
		if os.path.isfile(path+"/"+x):
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


	results.append(_("Found %(count)s locks") % {"count":mycount})
	
	for x in mylist:
		if myhost in mylist[x] or remove_all_locks:
			mylockname = hardlock_name(path+"/"+x)
			if hardlink_is_mine(mylockname, path+"/"+x) or \
			   not os.path.exists(path+"/"+x) or \
				 remove_all_locks:
				for y in mylist[x]:
					for z in mylist[x][y]:
						filename = path+"/."+x+".hardlock-"+y+"-"+z
						if filename == mylockname:
							continue
						try:
							# We're sweeping through, unlinking everyone's locks.
							os.unlink(filename)
							results.append(_("Unlinked: ") + filename)
						except OSError:
							pass
				try:
					os.unlink(path+"/"+x)
					results.append(_("Unlinked: ") + path+"/"+x)
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

