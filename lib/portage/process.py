# portage.py -- core Portage functionality
# Copyright 1998-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2


import atexit
import errno
import fcntl
import platform
import signal
import socket
import struct
import sys
import traceback
import os as _os

from portage import os
from portage import _encodings
from portage import _unicode_encode
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util:dump_traceback,writemsg',
)

from portage.const import BASH_BINARY, SANDBOX_BINARY, FAKEROOT_BINARY
from portage.exception import CommandNotFound
from portage.util._ctypes import find_library, LoadLibrary, ctypes

try:
	import resource
	max_fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
except ImportError:
	max_fd_limit = 256

if sys.hexversion >= 0x3000000:
	# pylint: disable=W0622
	basestring = str

# Support PEP 446 for Python >=3.4
try:
	_set_inheritable = _os.set_inheritable
except AttributeError:
	_set_inheritable = None

try:
	_FD_CLOEXEC = fcntl.FD_CLOEXEC
except AttributeError:
	_FD_CLOEXEC = None

# Prefer /proc/self/fd if available (/dev/fd
# doesn't work on solaris, see bug #474536).
for _fd_dir in ("/proc/self/fd", "/dev/fd"):
	if os.path.isdir(_fd_dir):
		break
	else:
		_fd_dir = None

# /dev/fd does not work on FreeBSD, see bug #478446
if platform.system() in ('FreeBSD',) and _fd_dir == '/dev/fd':
	_fd_dir = None

if _fd_dir is not None:
	def get_open_fds():
		return (int(fd) for fd in os.listdir(_fd_dir) if fd.isdigit())

	if platform.python_implementation() == 'PyPy':
		# EAGAIN observed with PyPy 1.8.
		_get_open_fds = get_open_fds
		def get_open_fds():
			try:
				return _get_open_fds()
			except OSError as e:
				if e.errno != errno.EAGAIN:
					raise
				return range(max_fd_limit)

elif os.path.isdir("/proc/%s/fd" % os.getpid()):
	# In order for this function to work in forked subprocesses,
	# os.getpid() must be called from inside the function.
	def get_open_fds():
		return (int(fd) for fd in os.listdir("/proc/%s/fd" % os.getpid())
			if fd.isdigit())

else:
	def get_open_fds():
		return range(max_fd_limit)

sandbox_capable = (os.path.isfile(SANDBOX_BINARY) and
                   os.access(SANDBOX_BINARY, os.X_OK))

fakeroot_capable = (os.path.isfile(FAKEROOT_BINARY) and
                    os.access(FAKEROOT_BINARY, os.X_OK))


def sanitize_fds():
	"""
	Set the inheritable flag to False for all open file descriptors,
	except for those corresponding to stdin, stdout, and stderr. This
	ensures that any unintentionally inherited file descriptors will
	not be inherited by child processes.
	"""
	if _set_inheritable is not None:

		whitelist = frozenset([
			sys.__stdin__.fileno(),
			sys.__stdout__.fileno(),
			sys.__stderr__.fileno(),
		])

		for fd in get_open_fds():
			if fd not in whitelist:
				try:
					_set_inheritable(fd, False)
				except OSError:
					pass


def spawn_bash(mycommand, debug=False, opt_name=None, **keywords):
	"""
	Spawns a bash shell running a specific commands
	
	@param mycommand: The command for bash to run
	@type mycommand: String
	@param debug: Turn bash debugging on (set -x)
	@type debug: Boolean
	@param opt_name: Name of the spawned process (detaults to binary name)
	@type opt_name: String
	@param keywords: Extra Dictionary arguments to pass to spawn
	@type keywords: Dictionary
	"""

	args = [BASH_BINARY]
	if not opt_name:
		opt_name = os.path.basename(mycommand.split()[0])
	if debug:
		# Print commands and their arguments as they are executed.
		args.append("-x")
	args.append("-c")
	args.append(mycommand)
	return spawn(args, opt_name=opt_name, **keywords)

def spawn_sandbox(mycommand, opt_name=None, **keywords):
	if not sandbox_capable:
		return spawn_bash(mycommand, opt_name=opt_name, **keywords)
	args = [SANDBOX_BINARY]
	if not opt_name:
		opt_name = os.path.basename(mycommand.split()[0])
	args.append(mycommand)
	return spawn(args, opt_name=opt_name, **keywords)

def spawn_fakeroot(mycommand, fakeroot_state=None, opt_name=None, **keywords):
	args = [FAKEROOT_BINARY]
	if not opt_name:
		opt_name = os.path.basename(mycommand.split()[0])
	if fakeroot_state:
		open(fakeroot_state, "a").close()
		args.append("-s")
		args.append(fakeroot_state)
		args.append("-i")
		args.append(fakeroot_state)
	args.append("--")
	args.append(BASH_BINARY)
	args.append("-c")
	args.append(mycommand)
	return spawn(args, opt_name=opt_name, **keywords)

_exithandlers = []
def atexit_register(func, *args, **kargs):
	"""Wrapper around atexit.register that is needed in order to track
	what is registered.  For example, when portage restarts itself via
	os.execv, the atexit module does not work so we have to do it
	manually by calling the run_exitfuncs() function in this module."""
	_exithandlers.append((func, args, kargs))

def run_exitfuncs():
	"""This should behave identically to the routine performed by
	the atexit module at exit time.  It's only necessary to call this
	function when atexit will not work (because of os.execv, for
	example)."""

	# This function is a copy of the private atexit._run_exitfuncs()
	# from the python 2.4.2 sources.  The only difference from the
	# original function is in the output to stderr.
	exc_info = None
	while _exithandlers:
		func, targs, kargs = _exithandlers.pop()
		try:
			func(*targs, **kargs)
		except SystemExit:
			exc_info = sys.exc_info()
		except: # No idea what they called, so we need this broad except here.
			dump_traceback("Error in portage.process.run_exitfuncs", noiselevel=0)
			exc_info = sys.exc_info()

	if exc_info is not None:
		if sys.hexversion >= 0x3000000:
			raise exc_info[0](exc_info[1]).with_traceback(exc_info[2])
		else:
			exec("raise exc_info[0], exc_info[1], exc_info[2]")

atexit.register(run_exitfuncs)

# It used to be necessary for API consumers to remove pids from spawned_pids,
# since otherwise it would accumulate a pids endlessly. Now, spawned_pids is
# just an empty dummy list, so for backward compatibility, ignore ValueError
# for removal on non-existent items.
class _dummy_list(list):
	def remove(self, item):
		# TODO: Trigger a DeprecationWarning here, after stable portage
		# has dummy spawned_pids.
		try:
			list.remove(self, item)
		except ValueError:
			pass

spawned_pids = _dummy_list()

def cleanup():
	pass

def spawn(mycommand, env={}, opt_name=None, fd_pipes=None, returnpid=False,
          uid=None, gid=None, groups=None, umask=None, logfile=None,
          path_lookup=True, pre_exec=None,
          close_fds=(sys.version_info < (3, 4)), unshare_net=False,
          unshare_ipc=False, cgroup=None):
	"""
	Spawns a given command.
	
	@param mycommand: the command to execute
	@type mycommand: String or List (Popen style list)
	@param env: A dict of Key=Value pairs for env variables
	@type env: Dictionary
	@param opt_name: an optional name for the spawn'd process (defaults to the binary name)
	@type opt_name: String
	@param fd_pipes: A dict of mapping for pipes, { '0': stdin, '1': stdout } for example
		(default is {0:stdin, 1:stdout, 2:stderr})
	@type fd_pipes: Dictionary
	@param returnpid: Return the Process IDs for a successful spawn.
	NOTE: This requires the caller clean up all the PIDs, otherwise spawn will clean them.
	@type returnpid: Boolean
	@param uid: User ID to spawn as; useful for dropping privilages
	@type uid: Integer
	@param gid: Group ID to spawn as; useful for dropping privilages
	@type gid: Integer
	@param groups: Group ID's to spawn in: useful for having the process run in multiple group contexts.
	@type groups: List
	@param umask: An integer representing the umask for the process (see man chmod for umask details)
	@type umask: Integer
	@param logfile: name of a file to use for logging purposes
	@type logfile: String
	@param path_lookup: If the binary is not fully specified then look for it in PATH
	@type path_lookup: Boolean
	@param pre_exec: A function to be called with no arguments just prior to the exec call.
	@type pre_exec: callable
	@param close_fds: If True, then close all file descriptors except those
		referenced by fd_pipes (default is True for python3.3 and earlier, and False for
		python3.4 and later due to non-inheritable file descriptor behavior from PEP 446).
	@type close_fds: Boolean
	@param unshare_net: If True, networking will be unshared from the spawned process
	@type unshare_net: Boolean
	@param unshare_ipc: If True, IPC will be unshared from the spawned process
	@type unshare_ipc: Boolean
	@param cgroup: CGroup path to bind the process to
	@type cgroup: String

	logfile requires stdout and stderr to be assigned to this process (ie not pointed
	   somewhere else.)
	
	"""

	# mycommand is either a str or a list
	if isinstance(mycommand, basestring):
		mycommand = mycommand.split()

	if sys.hexversion < 0x3000000:
		# Avoid a potential UnicodeEncodeError from os.execve().
		env_bytes = {}
		for k, v in env.items():
			env_bytes[_unicode_encode(k, encoding=_encodings['content'])] = \
				_unicode_encode(v, encoding=_encodings['content'])
		env = env_bytes
		del env_bytes

	# If an absolute path to an executable file isn't given
	# search for it unless we've been told not to.
	binary = mycommand[0]
	if binary not in (BASH_BINARY, SANDBOX_BINARY, FAKEROOT_BINARY) and \
		(not os.path.isabs(binary) or not os.path.isfile(binary)
	    or not os.access(binary, os.X_OK)):
		binary = path_lookup and find_binary(binary) or None
		if not binary:
			raise CommandNotFound(mycommand[0])

	# If we haven't been told what file descriptors to use
	# default to propagating our stdin, stdout and stderr.
	if fd_pipes is None:
		fd_pipes = {
			0:portage._get_stdin().fileno(),
			1:sys.__stdout__.fileno(),
			2:sys.__stderr__.fileno(),
		}

	# mypids will hold the pids of all processes created.
	mypids = []

	if logfile:
		# Using a log file requires that stdout and stderr
		# are assigned to the process we're running.
		if 1 not in fd_pipes or 2 not in fd_pipes:
			raise ValueError(fd_pipes)

		# Create a pipe
		(pr, pw) = os.pipe()

		# Create a tee process, giving it our stdout and stderr
		# as well as the read end of the pipe.
		mypids.extend(spawn(('tee', '-i', '-a', logfile),
		              returnpid=True, fd_pipes={0:pr,
		              1:fd_pipes[1], 2:fd_pipes[2]}))

		# We don't need the read end of the pipe, so close it.
		os.close(pr)

		# Assign the write end of the pipe to our stdout and stderr.
		fd_pipes[1] = pw
		fd_pipes[2] = pw

	# This caches the libc library lookup in the current
	# process, so that it's only done once rather than
	# for each child process.
	if unshare_net or unshare_ipc:
		find_library("c")

	# Force instantiation of portage.data.userpriv_groups before the
	# fork, so that the result is cached in the main process.
	bool(groups)

	parent_pid = os.getpid()
	pid = None
	try:
		pid = os.fork()

		if pid == 0:
			try:
				_exec(binary, mycommand, opt_name, fd_pipes,
					env, gid, groups, uid, umask, pre_exec, close_fds,
					unshare_net, unshare_ipc, cgroup)
			except SystemExit:
				raise
			except Exception as e:
				# We need to catch _any_ exception so that it doesn't
				# propagate out of this function and cause exiting
				# with anything other than os._exit()
				writemsg("%s:\n   %s\n" % (e, " ".join(mycommand)),
					noiselevel=-1)
				traceback.print_exc()
				sys.stderr.flush()

	finally:
		if pid == 0 or (pid is None and os.getpid() != parent_pid):
			# Call os._exit() from a finally block in order
			# to suppress any finally blocks from earlier
			# in the call stack (see bug #345289). This
			# finally block has to be setup before the fork
			# in order to avoid a race condition.
			os._exit(1)

	if not isinstance(pid, int):
		raise AssertionError("fork returned non-integer: %s" % (repr(pid),))

	# Add the pid to our local and the global pid lists.
	mypids.append(pid)

	# If we started a tee process the write side of the pipe is no
	# longer needed, so close it.
	if logfile:
		os.close(pw)

	# If the caller wants to handle cleaning up the processes, we tell
	# it about all processes that were created.
	if returnpid:
		return mypids

	# Otherwise we clean them up.
	while mypids:

		# Pull the last reader in the pipe chain. If all processes
		# in the pipe are well behaved, it will die when the process
		# it is reading from dies.
		pid = mypids.pop(0)

		# and wait for it.
		retval = os.waitpid(pid, 0)[1]

		if retval:
			# If it failed, kill off anything else that
			# isn't dead yet.
			for pid in mypids:
				# With waitpid and WNOHANG, only check the
				# first element of the tuple since the second
				# element may vary (bug #337465).
				if os.waitpid(pid, os.WNOHANG)[0] == 0:
					os.kill(pid, signal.SIGTERM)
					os.waitpid(pid, 0)

			# If it got a signal, return the signal that was sent.
			if (retval & 0xff):
				return ((retval & 0xff) << 8)

			# Otherwise, return its exit code.
			return (retval >> 8)

	# Everything succeeded
	return 0

def _exec(binary, mycommand, opt_name, fd_pipes, env, gid, groups, uid, umask,
	pre_exec, close_fds, unshare_net, unshare_ipc, cgroup):

	"""
	Execute a given binary with options
	
	@param binary: Name of program to execute
	@type binary: String
	@param mycommand: Options for program
	@type mycommand: String
	@param opt_name: Name of process (defaults to binary)
	@type opt_name: String
	@param fd_pipes: Mapping pipes to destination; { 0:0, 1:1, 2:2 }
	@type fd_pipes: Dictionary
	@param env: Key,Value mapping for Environmental Variables
	@type env: Dictionary
	@param gid: Group ID to run the process under
	@type gid: Integer
	@param groups: Groups the Process should be in.
	@type groups: Integer
	@param uid: User ID to run the process under
	@type uid: Integer
	@param umask: an int representing a unix umask (see man chmod for umask details)
	@type umask: Integer
	@param pre_exec: A function to be called with no arguments just prior to the exec call.
	@type pre_exec: callable
	@param unshare_net: If True, networking will be unshared from the spawned process
	@type unshare_net: Boolean
	@param unshare_ipc: If True, IPC will be unshared from the spawned process
	@type unshare_ipc: Boolean
	@param cgroup: CGroup path to bind the process to
	@type cgroup: String
	@rtype: None
	@return: Never returns (calls os.execve)
	"""

	# If the process we're creating hasn't been given a name
	# assign it the name of the executable.
	if not opt_name:
		if binary is portage._python_interpreter:
			# NOTE: PyPy 1.7 will die due to "libary path not found" if argv[0]
			# does not contain the full path of the binary.
			opt_name = binary
		else:
			opt_name = os.path.basename(binary)

	# Set up the command's argument list.
	myargs = [opt_name]
	myargs.extend(mycommand[1:])

	# Avoid a potential UnicodeEncodeError from os.execve().
	myargs = [_unicode_encode(x, encoding=_encodings['fs'],
		errors='strict') for x in myargs]

	# Use default signal handlers in order to avoid problems
	# killing subprocesses as reported in bug #353239.
	signal.signal(signal.SIGINT, signal.SIG_DFL)
	signal.signal(signal.SIGTERM, signal.SIG_DFL)

	# Unregister SIGCHLD handler and wakeup_fd for the parent
	# process's event loop (bug 655656).
	signal.signal(signal.SIGCHLD, signal.SIG_DFL)
	try:
		wakeup_fd = signal.set_wakeup_fd(-1)
		if wakeup_fd > 0:
			os.close(wakeup_fd)
	except (ValueError, OSError):
		pass

	# Quiet killing of subprocesses by SIGPIPE (see bug #309001).
	signal.signal(signal.SIGPIPE, signal.SIG_DFL)

	# Avoid issues triggered by inheritance of SIGQUIT handler from
	# the parent process (see bug #289486).
	signal.signal(signal.SIGQUIT, signal.SIG_DFL)

	_setup_pipes(fd_pipes, close_fds=close_fds, inheritable=True)

	# Add to cgroup
	# it's better to do it from the child since we can guarantee
	# it is done before we start forking children
	if cgroup:
		with open(os.path.join(cgroup, 'cgroup.procs'), 'a') as f:
			f.write('%d\n' % os.getpid())

	# Unshare (while still uid==0)
	if unshare_net or unshare_ipc:
		filename = find_library("c")
		if filename is not None:
			libc = LoadLibrary(filename)
			if libc is not None:
				CLONE_NEWIPC = 0x08000000
				CLONE_NEWNET = 0x40000000

				flags = 0
				if unshare_net:
					flags |= CLONE_NEWNET
				if unshare_ipc:
					flags |= CLONE_NEWIPC

				try:
					if libc.unshare(flags) != 0:
						writemsg("Unable to unshare: %s\n" % (
							errno.errorcode.get(ctypes.get_errno(), '?')),
							noiselevel=-1)
					else:
						if unshare_net:
							# 'up' the loopback
							IFF_UP = 0x1
							ifreq = struct.pack('16sh', b'lo', IFF_UP)
							SIOCSIFFLAGS = 0x8914

							sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
							try:
								fcntl.ioctl(sock, SIOCSIFFLAGS, ifreq)
							except IOError as e:
								writemsg("Unable to enable loopback interface: %s\n" % (
									errno.errorcode.get(e.errno, '?')),
									noiselevel=-1)
							sock.close()
				except AttributeError:
					# unshare() not supported by libc
					pass

	# Set requested process permissions.
	if gid:
		# Cast proxies to int, in case it matters.
		os.setgid(int(gid))
	if groups:
		os.setgroups(groups)
	if uid:
		# Cast proxies to int, in case it matters.
		os.setuid(int(uid))
	if umask:
		os.umask(umask)
	if pre_exec:
		pre_exec()

	# And switch to the new process.
	os.execve(binary, myargs, env)

def _setup_pipes(fd_pipes, close_fds=True, inheritable=None):
	"""Setup pipes for a forked process.

	Even when close_fds is False, file descriptors referenced as
	values in fd_pipes are automatically closed if they do not also
	occur as keys in fd_pipes. It is assumed that the caller will
	explicitly add them to the fd_pipes keys if they are intended
	to remain open. This allows for convenient elimination of
	unnecessary duplicate file descriptors.

	WARNING: When not followed by exec, the close_fds behavior
	can trigger interference from destructors that close file
	descriptors. This interference happens when the garbage
	collector intermittently executes such destructors after their
	corresponding file descriptors have been re-used, leading
	to intermittent "[Errno 9] Bad file descriptor" exceptions in
	forked processes. This problem has been observed with PyPy 1.8,
	and also with CPython under some circumstances (as triggered
	by xmpppy in bug #374335). In order to close a safe subset of
	file descriptors, see portage.locks._close_fds().

	NOTE: When not followed by exec, even when close_fds is False,
	it's still possible for dup2() calls to cause interference in a
	way that's similar to the way that close_fds interferes (since
	dup2() has to close the target fd if it happens to be open).
	It's possible to avoid such interference by using allocated
	file descriptors as the keys in fd_pipes. For example:

		pr, pw = os.pipe()
		fd_pipes[pw] = pw

	By using the allocated pw file descriptor as the key in fd_pipes,
	it's not necessary for dup2() to close a file descriptor (it
	actually does nothing in this case), which avoids possible
	interference.
	"""

	reverse_map = {}
	# To protect from cases where direct assignment could
	# clobber needed fds ({1:2, 2:1}) we create a reverse map
	# in order to know when it's necessary to create temporary
	# backup copies with os.dup().
	for newfd, oldfd in fd_pipes.items():
		newfds = reverse_map.get(oldfd)
		if newfds is None:
			newfds = []
			reverse_map[oldfd] = newfds
		newfds.append(newfd)

	# Assign newfds via dup2(), making temporary backups when
	# necessary, and closing oldfd if the caller has not
	# explicitly requested for it to remain open by adding
	# it to the keys of fd_pipes.
	while reverse_map:

		oldfd, newfds = reverse_map.popitem()
		old_fdflags = None

		for newfd in newfds:
			if newfd in reverse_map:
				# Make a temporary backup before re-assignment, assuming
				# that backup_fd won't collide with a key in reverse_map
				# (since all of the keys correspond to open file
				# descriptors, and os.dup() only allocates a previously
				# unused file discriptors).
				backup_fd = os.dup(newfd)
				reverse_map[backup_fd] = reverse_map.pop(newfd)

			if oldfd != newfd:
				os.dup2(oldfd, newfd)
				if _set_inheritable is not None:
					# Don't do this unless _set_inheritable is available,
					# since it's used below to ensure correct state, and
					# otherwise /dev/null stdin fails to inherit (at least
					# with Python versions from 3.1 to 3.3).
					if old_fdflags is None:
						old_fdflags = fcntl.fcntl(oldfd, fcntl.F_GETFD)
					fcntl.fcntl(newfd, fcntl.F_SETFD, old_fdflags)

			if _set_inheritable is not None:

				inheritable_state = None
				if not (old_fdflags is None or _FD_CLOEXEC is None):
					inheritable_state = not bool(old_fdflags & _FD_CLOEXEC)

				if inheritable is not None:
					if inheritable_state is not inheritable:
						_set_inheritable(newfd, inheritable)

				elif newfd in (0, 1, 2):
					if inheritable_state is not True:
						_set_inheritable(newfd, True)

		if oldfd not in fd_pipes:
			# If oldfd is not a key in fd_pipes, then it's safe
			# to close now, since we've already made all of the
			# requested duplicates. This also closes every
			# backup_fd that may have been created on previous
			# iterations of this loop.
			os.close(oldfd)

	if close_fds:
		# Then close _all_ fds that haven't been explicitly
		# requested to be kept open.
		for fd in get_open_fds():
			if fd not in fd_pipes:
				try:
					os.close(fd)
				except OSError:
					pass

def find_binary(binary):
	"""
	Given a binary name, find the binary in PATH
	
	@param binary: Name of the binary to find
	@type string
	@rtype: None or string
	@return: full path to binary or None if the binary could not be located.
	"""
	paths = os.environ.get("PATH", "")
	if sys.hexversion >= 0x3000000 and isinstance(binary, bytes):
		# return bytes when input is bytes
		paths = paths.encode(sys.getfilesystemencoding(), 'surrogateescape')
		paths = paths.split(b':')
	else:
		paths = paths.split(':')

	for path in paths:
		filename = _os.path.join(path, binary)
		if _os.access(filename, os.X_OK) and _os.path.isfile(filename):
			return filename
	return None
