# portage.py -- core Portage functionality
# Copyright 1998-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2


import atexit
import errno
import platform
import signal
import sys
import traceback

from portage import os
from portage import _encodings
from portage import _unicode_encode
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util:dump_traceback',
)

from portage.const import BASH_BINARY, SANDBOX_BINARY, FAKEROOT_BINARY
from portage.exception import CommandNotFound

try:
	import resource
	max_fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
except ImportError:
	max_fd_limit = 256

if sys.hexversion >= 0x3000000:
	basestring = str

if os.path.isdir("/proc/%i/fd" % os.getpid()):
	def get_open_fds():
		return (int(fd) for fd in os.listdir("/proc/%i/fd" % os.getpid()) \
			if fd.isdigit())

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

else:
	def get_open_fds():
		return range(max_fd_limit)

sandbox_capable = (os.path.isfile(SANDBOX_BINARY) and
                   os.access(SANDBOX_BINARY, os.X_OK))

fakeroot_capable = (os.path.isfile(FAKEROOT_BINARY) and
                    os.access(FAKEROOT_BINARY, os.X_OK))

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
	args=[SANDBOX_BINARY]
	if not opt_name:
		opt_name = os.path.basename(mycommand.split()[0])
	args.append(mycommand)
	return spawn(args, opt_name=opt_name, **keywords)

def spawn_fakeroot(mycommand, fakeroot_state=None, opt_name=None, **keywords):
	args=[FAKEROOT_BINARY]
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

# We need to make sure that any processes spawned are killed off when
# we exit. spawn() takes care of adding and removing pids to this list
# as it creates and cleans up processes.
spawned_pids = []
def cleanup():
	while spawned_pids:
		pid = spawned_pids.pop()
		try:
			# With waitpid and WNOHANG, only check the
			# first element of the tuple since the second
			# element may vary (bug #337465).
			if os.waitpid(pid, os.WNOHANG)[0] == 0:
				os.kill(pid, signal.SIGTERM)
				os.waitpid(pid, 0)
		except OSError:
			# This pid has been cleaned up outside
			# of spawn().
			pass

atexit_register(cleanup)

def spawn(mycommand, env={}, opt_name=None, fd_pipes=None, returnpid=False,
          uid=None, gid=None, groups=None, umask=None, logfile=None,
          path_lookup=True, pre_exec=None):
	"""
	Spawns a given command.
	
	@param mycommand: the command to execute
	@type mycommand: String or List (Popen style list)
	@param env: A dict of Key=Value pairs for env variables
	@type env: Dictionary
	@param opt_name: an optional name for the spawn'd process (defaults to the binary name)
	@type opt_name: String
	@param fd_pipes: A dict of mapping for pipes, { '0': stdin, '1': stdout } for example
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
			0:sys.__stdin__.fileno(),
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

	pid = os.fork()

	if pid == 0:
		try:
			_exec(binary, mycommand, opt_name, fd_pipes,
			      env, gid, groups, uid, umask, pre_exec)
		except SystemExit:
			raise
		except Exception as e:
			# We need to catch _any_ exception so that it doesn't
			# propagate out of this function and cause exiting
			# with anything other than os._exit()
			sys.stderr.write("%s:\n   %s\n" % (e, " ".join(mycommand)))
			traceback.print_exc()
			sys.stderr.flush()
			os._exit(1)

	if not isinstance(pid, int):
		raise AssertionError("fork returned non-integer: %s" % (repr(pid),))

	# Add the pid to our local and the global pid lists.
	mypids.append(pid)
	spawned_pids.append(pid)

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

		# When it's done, we can remove it from the
		# global pid list as well.
		spawned_pids.remove(pid)

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
				spawned_pids.remove(pid)

			# If it got a signal, return the signal that was sent.
			if (retval & 0xff):
				return ((retval & 0xff) << 8)

			# Otherwise, return its exit code.
			return (retval >> 8)

	# Everything succeeded
	return 0

def _exec(binary, mycommand, opt_name, fd_pipes, env, gid, groups, uid, umask,
	pre_exec):

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

	# Use default signal handlers in order to avoid problems
	# killing subprocesses as reported in bug #353239.
	signal.signal(signal.SIGINT, signal.SIG_DFL)
	signal.signal(signal.SIGTERM, signal.SIG_DFL)

	# Quiet killing of subprocesses by SIGPIPE (see bug #309001).
	signal.signal(signal.SIGPIPE, signal.SIG_DFL)

	# Avoid issues triggered by inheritance of SIGQUIT handler from
	# the parent process (see bug #289486).
	signal.signal(signal.SIGQUIT, signal.SIG_DFL)

	_setup_pipes(fd_pipes)

	# Set requested process permissions.
	if gid:
		os.setgid(gid)
	if groups:
		os.setgroups(groups)
	if uid:
		os.setuid(uid)
	if umask:
		os.umask(umask)
	if pre_exec:
		pre_exec()

	# And switch to the new process.
	os.execve(binary, myargs, env)

def _setup_pipes(fd_pipes, close_fds=True):
	"""Setup pipes for a forked process.

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
	"""
	my_fds = {}
	# To protect from cases where direct assignment could
	# clobber needed fds ({1:2, 2:1}) we first dupe the fds
	# into unused fds.
	for fd in fd_pipes:
		my_fds[fd] = os.dup(fd_pipes[fd])
	# Then assign them to what they should be.
	for fd in my_fds:
		os.dup2(my_fds[fd], fd)

	if close_fds:
		# Then close _all_ fds that haven't been explicitly
		# requested to be kept open.
		for fd in get_open_fds():
			if fd not in my_fds:
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
	for path in os.environ.get("PATH", "").split(":"):
		filename = "%s/%s" % (path, binary)
		if os.access(filename, os.X_OK) and os.path.isfile(filename):
			return filename
	return None
