# portage: Lock management code
# Copyright 2004-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ["lockdir", "unlockdir", "lockfile", "unlockfile", \
	"hardlock_name", "hardlink_is_mine", "hardlink_lockfile", \
	"unhardlink_lockfile", "hardlock_cleanup"]

import errno
import fcntl
import platform
import stat
import sys
import time

import portage
from portage import os
from portage.const import PORTAGE_BIN_PATH
from portage.exception import DirectoryNotFound, FileNotFound, \
	InvalidData, TryAgain, OperationNotPermitted, PermissionDenied
from portage.data import portage_gid
from portage.util import writemsg
from portage.localization import _

if sys.hexversion >= 0x3000000:
	basestring = str

HARDLINK_FD = -2
_default_lock_fn = fcntl.lockf

if platform.python_implementation() == 'PyPy':
	# workaround for https://bugs.pypy.org/issue747
	_default_lock_fn = fcntl.flock

# Used by emerge in order to disable the "waiting for lock" message
# so that it doesn't interfere with the status display.
_quiet = False

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

	if isinstance(mypath, basestring) and mypath[-1] == '/':
		mypath = mypath[:-1]

	if hasattr(mypath, 'fileno'):
		mypath = mypath.fileno()
	if isinstance(mypath, int):
		lockfilename    = mypath
		wantnewlockfile = 0
		unlinkfile      = 0
	elif wantnewlockfile:
		base, tail = os.path.split(mypath)
		lockfilename = os.path.join(base, "." + tail + ".portage_lockfile")
		del base, tail
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
		elif e.errno == errno.ENOLCK:
			# We're not allowed to lock on this FS.
			os.close(myfd)
			link_success = False
			if lockfilename == str(lockfilename):
				if wantnewlockfile:
					try:
						if os.stat(lockfilename)[stat.ST_NLINK] == 1:
							os.unlink(lockfilename)
					except OSError:
						pass
					link_success = hardlink_lockfile(lockfilename)
			if not link_success:
				raise
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
		unhardlink_lockfile(lockfilename)
		return True
	
	# myfd may be None here due to myfd = mypath in lockfile()
	if isinstance(lockfilename, basestring) and \
		not os.path.exists(lockfilename):
		writemsg(_("lockfile does not exist '%s'\n") % lockfilename,1)
		if myfd is not None:
			os.close(myfd)
		return False

	try:
		if myfd is None:
			myfd = os.open(lockfilename, os.O_WRONLY,0o660)
			unlinkfile = 1
		locking_method(myfd,fcntl.LOCK_UN)
	except OSError:
		if isinstance(lockfilename, basestring):
			os.close(myfd)
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

	return True




def hardlock_name(path):
	return path+".hardlock-"+os.uname()[1]+"-"+str(os.getpid())

def hardlink_is_mine(link,lock):
	try:
		return os.stat(link).st_nlink == 2
	except OSError:
		return False

def hardlink_lockfile(lockfilename, max_wait=14400):
	"""Does the NFS, hardlink shuffle to ensure locking on the disk.
	We create a PRIVATE lockfile, that is just a placeholder on the disk.
	Then we HARDLINK the real lockfile to that private file.
	If our file can 2 references, then we have the lock. :)
	Otherwise we lather, rise, and repeat.
	We default to a 4 hour timeout.
	"""

	start_time = time.time()
	myhardlock = hardlock_name(lockfilename)
	reported_waiting = False
	
	while(time.time() < (start_time + max_wait)):
		# We only need it to exist.
		myfd = os.open(myhardlock, os.O_CREAT|os.O_RDWR,0o660)
		os.close(myfd)
	
		if not os.path.exists(myhardlock):
			raise FileNotFound(
				_("Created lockfile is missing: %(filename)s") % \
				{"filename" : myhardlock})

		try:
			res = os.link(myhardlock, lockfilename)
		except OSError:
			pass

		if hardlink_is_mine(myhardlock, lockfilename):
			# We have the lock.
			if reported_waiting:
				writemsg("\n", noiselevel=-1)
			return True

		if reported_waiting:
			writemsg(".", noiselevel=-1)
		else:
			reported_waiting = True
			msg = _("\nWaiting on (hardlink) lockfile: (one '.' per 3 seconds)\n"
				"%(bin_path)s/clean_locks can fix stuck locks.\n"
				"Lockfile: %(lockfilename)s\n") % \
				{"bin_path": PORTAGE_BIN_PATH, "lockfilename": lockfilename}
			writemsg(msg, noiselevel=-1)
		time.sleep(3)
	
	os.unlink(myhardlock)
	return False

def unhardlink_lockfile(lockfilename):
	myhardlock = hardlock_name(lockfilename)
	if hardlink_is_mine(myhardlock, lockfilename):
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
				filename = parts[0]
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
						filename = path+"/"+x+".hardlock-"+y+"-"+z
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

