# Copyright 1999-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys
import logging
import time
import signal
import socket
import re
import random
import tempfile

import portage
from portage import os
from portage import _unicode_decode
from portage.util import writemsg_level
from portage.output import create_color_func, yellow, blue, bold
good = create_color_func("GOOD")
bad = create_color_func("BAD")
warn = create_color_func("WARN")
from portage.const import VCS_DIRS, TIMESTAMP_FORMAT, RSYNC_PACKAGE_ATOM
from portage.util import writemsg, writemsg_stdout
from portage.sync.getaddrinfo_validate import getaddrinfo_validate
from _emerge.UserQuery import UserQuery
from portage.sync.syncbase import NewBase

if sys.hexversion >= 0x3000000:
	# pylint: disable=W0622
	_unicode = str
else:
	_unicode = unicode

SERVER_OUT_OF_DATE = -1
EXCEEDED_MAX_RETRIES = -2


class RsyncSync(NewBase):
	'''Rsync sync module'''

	short_desc = "Perform sync operations on rsync based repositories"

	@staticmethod
	def name():
		return "RsyncSync"


	def __init__(self):
		NewBase.__init__(self, "rsync", RSYNC_PACKAGE_ATOM)


	def update(self):
		'''Internal update function which performs the transfer'''
		opts = self.options.get('emerge_config').opts
		self.usersync_uid = self.options.get('usersync_uid', None)
		enter_invalid = '--ask-enter-invalid' in opts
		out = portage.output.EOutput()
		syncuri = self.repo.sync_uri
		if self.repo.module_specific_options.get(
			'sync-rsync-vcs-ignore', 'false').lower() == 'true':
			vcs_dirs = ()
		else:
			vcs_dirs = frozenset(VCS_DIRS)
			vcs_dirs = vcs_dirs.intersection(os.listdir(self.repo.location))

		for vcs_dir in vcs_dirs:
			writemsg_level(("!!! %s appears to be under revision " + \
				"control (contains %s).\n!!! Aborting rsync sync "
				"(override with \"sync-rsync-vcs-ignore = true\" in repos.conf).\n") % \
				(self.repo.location, vcs_dir), level=logging.ERROR, noiselevel=-1)
			return (1, False)
		self.timeout=180

		rsync_opts = []
		if self.settings["PORTAGE_RSYNC_OPTS"] == "":
			rsync_opts = self._set_rsync_defaults()
		else:
			rsync_opts = self._validate_rsync_opts(rsync_opts, syncuri)
		self.rsync_opts = self._rsync_opts_extend(opts, rsync_opts)

		self.extra_rsync_opts = list()
		if self.repo.module_specific_options.get('sync-rsync-extra-opts'):
			self.extra_rsync_opts.extend(portage.util.shlex_split(
				self.repo.module_specific_options['sync-rsync-extra-opts']))

		# Real local timestamp file.
		self.servertimestampfile = os.path.join(
			self.repo.location, "metadata", "timestamp.chk")

		content = portage.util.grabfile(self.servertimestampfile)
		timestamp = 0
		if content:
			try:
				timestamp = time.mktime(time.strptime(content[0],
					TIMESTAMP_FORMAT))
			except (OverflowError, ValueError):
				pass
		del content

		try:
			self.rsync_initial_timeout = \
				int(self.settings.get("PORTAGE_RSYNC_INITIAL_TIMEOUT", "15"))
		except ValueError:
			self.rsync_initial_timeout = 15

		try:
			maxretries=int(self.settings["PORTAGE_RSYNC_RETRIES"])
		except SystemExit as e:
			raise # Needed else can't exit
		except:
			maxretries = -1 #default number of retries

		if syncuri.startswith("file://"):
			self.proto = "file"
			dosyncuri = syncuri[6:]
			is_synced, exitcode, updatecache_flg = self._do_rsync(
				dosyncuri, timestamp, opts)
			self._process_exitcode(exitcode, dosyncuri, out, 1)
			return (exitcode, updatecache_flg)

		retries=0
		try:
			self.proto, user_name, hostname, port = re.split(
				r"(rsync|ssh)://([^:/]+@)?(\[[:\da-fA-F]*\]|[^:/]*)(:[0-9]+)?",
				syncuri, maxsplit=4)[1:5]
		except ValueError:
			writemsg_level("!!! sync-uri is invalid: %s\n" % syncuri,
				noiselevel=-1, level=logging.ERROR)
			return (1, False)

		self.ssh_opts = self.settings.get("PORTAGE_SSH_OPTS")

		if port is None:
			port=""
		if user_name is None:
			user_name=""
		if re.match(r"^\[[:\da-fA-F]*\]$", hostname) is None:
			getaddrinfo_host = hostname
		else:
			# getaddrinfo needs the brackets stripped
			getaddrinfo_host = hostname[1:-1]
		updatecache_flg = False
		all_rsync_opts = set(self.rsync_opts)
		all_rsync_opts.update(self.extra_rsync_opts)

		family = socket.AF_UNSPEC
		if "-4" in all_rsync_opts or "--ipv4" in all_rsync_opts:
			family = socket.AF_INET
		elif socket.has_ipv6 and \
			("-6" in all_rsync_opts or "--ipv6" in all_rsync_opts):
			family = socket.AF_INET6

		addrinfos = None
		uris = []

		try:
			addrinfos = getaddrinfo_validate(
				socket.getaddrinfo(getaddrinfo_host, None,
				family, socket.SOCK_STREAM))
		except socket.error as e:
			writemsg_level(
				"!!! getaddrinfo failed for '%s': %s\n"
				% (_unicode_decode(hostname), _unicode(e)),
				noiselevel=-1, level=logging.ERROR)

		if addrinfos:

			AF_INET = socket.AF_INET
			AF_INET6 = None
			if socket.has_ipv6:
				AF_INET6 = socket.AF_INET6

			ips_v4 = []
			ips_v6 = []

			for addrinfo in addrinfos:
				if addrinfo[0] == AF_INET:
					ips_v4.append("%s" % addrinfo[4][0])
				elif AF_INET6 is not None and addrinfo[0] == AF_INET6:
					# IPv6 addresses need to be enclosed in square brackets
					ips_v6.append("[%s]" % addrinfo[4][0])

			random.shuffle(ips_v4)
			random.shuffle(ips_v6)

			# Give priority to the address family that
			# getaddrinfo() returned first.
			if AF_INET6 is not None and addrinfos and \
				addrinfos[0][0] == AF_INET6:
				ips = ips_v6 + ips_v4
			else:
				ips = ips_v4 + ips_v6

			for ip in ips:
				uris.append(syncuri.replace(
					"//" + user_name + hostname + port + "/",
					"//" + user_name + ip + port + "/", 1))

		if not uris:
			# With some configurations we need to use the plain hostname
			# rather than try to resolve the ip addresses (bug #340817).
			uris.append(syncuri)

		# reverse, for use with pop()
		uris.reverse()

		effective_maxretries = maxretries
		if effective_maxretries < 0:
			effective_maxretries = len(uris) - 1

		while (1):
			if uris:
				dosyncuri = uris.pop()
			else:
				writemsg("!!! Exhausted addresses for %s\n"
					% _unicode_decode(hostname), noiselevel=-1)
				return (1, False)

			if (retries==0):
				if "--ask" in opts:
					uq = UserQuery(opts)
					if uq.query("Do you want to sync your Portage tree " + \
						"with the mirror at\n" + blue(dosyncuri) + bold("?"),
						enter_invalid) == "No":
						print()
						print("Quitting.")
						print()
						sys.exit(128 + signal.SIGINT)
				self.logger(self.xterm_titles,
					">>> Starting rsync with " + dosyncuri)
				if "--quiet" not in opts:
					print(">>> Starting rsync with "+dosyncuri+"...")
			else:
				self.logger(self.xterm_titles,
					">>> Starting retry %d of %d with %s" % \
						(retries, effective_maxretries, dosyncuri))
				writemsg_stdout(
					"\n\n>>> Starting retry %d of %d with %s\n" % \
					(retries, effective_maxretries, dosyncuri), noiselevel=-1)

			if dosyncuri.startswith('ssh://'):
				dosyncuri = dosyncuri[6:].replace('/', ':/', 1)

			is_synced, exitcode, updatecache_flg = self._do_rsync(
				dosyncuri, timestamp, opts)
			if is_synced:
				break

			retries=retries+1

			if maxretries < 0 or retries <= maxretries:
				print(">>> Retrying...")
			else:
				# over retries
				# exit loop
				exitcode = EXCEEDED_MAX_RETRIES
				break
		self._process_exitcode(exitcode, dosyncuri, out, maxretries)
		return (exitcode, updatecache_flg)


	def _process_exitcode(self, exitcode, syncuri, out, maxretries):
		if (exitcode==0):
			pass
		elif exitcode == SERVER_OUT_OF_DATE:
			exitcode = 1
		elif exitcode == EXCEEDED_MAX_RETRIES:
			sys.stderr.write(
				">>> Exceeded PORTAGE_RSYNC_RETRIES: %s\n" % maxretries)
			exitcode = 1
		elif (exitcode>0):
			msg = []
			if exitcode==1:
				msg.append("Rsync has reported that there is a syntax error. Please ensure")
				msg.append("that sync-uri attribute for repository '%s' is proper." % self.repo.name)
				msg.append("sync-uri: '%s'" % self.repo.sync_uri)
			elif exitcode==11:
				msg.append("Rsync has reported that there is a File IO error. Normally")
				msg.append("this means your disk is full, but can be caused by corruption")
				msg.append("on the filesystem that contains repository '%s'. Please investigate" % self.repo.name)
				msg.append("and try again after the problem has been fixed.")
				msg.append("Location of repository: '%s'" % self.repo.location)
			elif exitcode==20:
				msg.append("Rsync was killed before it finished.")
			else:
				msg.append("Rsync has not successfully finished. It is recommended that you keep")
				msg.append("trying or that you use the 'emerge-webrsync' option if you are unable")
				msg.append("to use rsync due to firewall or other restrictions. This should be a")
				msg.append("temporary problem unless complications exist with your network")
				msg.append("(and possibly your system's filesystem) configuration.")
			for line in msg:
				out.eerror(line)


	def new(self, **kwargs):
		if kwargs:
			self._kwargs(kwargs)
		try:
			if not os.path.exists(self.repo.location):
				os.makedirs(self.repo.location)
				self.logger(self.self.xterm_titles,
					'Created New Directory %s ' % self.repo.location )
		except IOError:
			return (1, False)
		return self.update()


	def _set_rsync_defaults(self):
		portage.writemsg("PORTAGE_RSYNC_OPTS empty or unset, using hardcoded defaults\n")
		rsync_opts = [
			"--recursive",    # Recurse directories
			"--links",        # Consider symlinks
			"--safe-links",   # Ignore links outside of tree
			"--perms",        # Preserve permissions
			"--times",        # Preserive mod times
			"--omit-dir-times",
			"--compress",     # Compress the data transmitted
			"--force",        # Force deletion on non-empty dirs
			"--whole-file",   # Don't do block transfers, only entire files
			"--delete",       # Delete files that aren't in the master tree
			"--stats",        # Show final statistics about what was transfered
			"--human-readable",
			"--timeout="+str(self.timeout), # IO timeout if not done in X seconds
			"--exclude=/distfiles",   # Exclude distfiles from consideration
			"--exclude=/local",       # Exclude local     from consideration
			"--exclude=/packages",    # Exclude packages  from consideration
		]
		return rsync_opts


	def _validate_rsync_opts(self, rsync_opts, syncuri):
		# The below validation is not needed when using the above hardcoded
		# defaults.

		portage.writemsg("Using PORTAGE_RSYNC_OPTS instead of hardcoded defaults\n", 1)
		rsync_opts.extend(portage.util.shlex_split(
			self.settings.get("PORTAGE_RSYNC_OPTS", "")))
		for opt in ("--recursive", "--times"):
			if opt not in rsync_opts:
				portage.writemsg(yellow("WARNING:") + " adding required option " + \
				"%s not included in PORTAGE_RSYNC_OPTS\n" % opt)
				rsync_opts.append(opt)

		for exclude in ("distfiles", "local", "packages"):
			opt = "--exclude=/%s" % exclude
			if opt not in rsync_opts:
				portage.writemsg(yellow("WARNING:") + \
				" adding required option %s not included in "  % opt + \
				"PORTAGE_RSYNC_OPTS (can be overridden with --exclude='!')\n")
				rsync_opts.append(opt)

		if syncuri.rstrip("/").endswith(".gentoo.org/gentoo-portage"):
			def rsync_opt_startswith(opt_prefix):
				for x in rsync_opts:
					if x.startswith(opt_prefix):
						return (1, False)
				return (0, False)

			if not rsync_opt_startswith("--timeout="):
				rsync_opts.append("--timeout=%d" % self.timeout)

			for opt in ("--compress", "--whole-file"):
				if opt not in rsync_opts:
					portage.writemsg(yellow("WARNING:") + " adding required option " + \
					"%s not included in PORTAGE_RSYNC_OPTS\n" % opt)
					rsync_opts.append(opt)
		return rsync_opts


	@staticmethod
	def _rsync_opts_extend(opts, rsync_opts):
		if "--quiet" in opts:
			rsync_opts.append("--quiet")    # Shut up a lot
		else:
			rsync_opts.append("--verbose")	# Print filelist

		if "--verbose" in opts:
			rsync_opts.append("--progress")  # Progress meter for each file

		if "--debug" in opts:
			rsync_opts.append("--checksum") # Force checksum on all files
		return rsync_opts


	def _do_rsync(self, syncuri, timestamp, opts):
		updatecache_flg = False
		is_synced = False
		if timestamp != 0 and "--quiet" not in opts:
			print(">>> Checking server timestamp ...")

		rsynccommand = [self.bin_command] + self.rsync_opts + self.extra_rsync_opts

		if self.proto == 'ssh' and self.ssh_opts:
			rsynccommand.append("--rsh=ssh " + self.ssh_opts)

		if "--debug" in opts:
			print(rsynccommand)

		exitcode = os.EX_OK
		servertimestamp = 0
		# Even if there's no timestamp available locally, fetch the
		# timestamp anyway as an initial probe to verify that the server is
		# responsive.  This protects us from hanging indefinitely on a
		# connection attempt to an unresponsive server which rsync's
		# --timeout option does not prevent.

		#if True:
		# Temporary file for remote server timestamp comparison.
		# NOTE: If FEATURES=usersync is enabled then the tempfile
		# needs to be in a directory that's readable by the usersync
		# user. We assume that PORTAGE_TMPDIR will satisfy this
		# requirement, since that's not necessarily true for the
		# default directory used by the tempfile module.
		if self.usersync_uid is not None:
			tmpdir = self.settings['PORTAGE_TMPDIR']
		else:
			# use default dir from tempfile module
			tmpdir = None
		fd, tmpservertimestampfile = \
			tempfile.mkstemp(dir=tmpdir)
		os.close(fd)
		if self.usersync_uid is not None:
			portage.util.apply_permissions(tmpservertimestampfile,
				uid=self.usersync_uid)
		command = rsynccommand[:]
		command.append(syncuri.rstrip("/") + \
			"/metadata/timestamp.chk")
		command.append(tmpservertimestampfile)
		content = None
		pids = []
		try:
			# Timeout here in case the server is unresponsive.  The
			# --timeout rsync option doesn't apply to the initial
			# connection attempt.
			try:
				if self.rsync_initial_timeout:
					portage.exception.AlarmSignal.register(
						self.rsync_initial_timeout)

				pids.extend(portage.process.spawn(
					command, returnpid=True,
					**self.spawn_kwargs))
				exitcode = os.waitpid(pids[0], 0)[1]
				if self.usersync_uid is not None:
					portage.util.apply_permissions(tmpservertimestampfile,
						uid=os.getuid())
				content = portage.grabfile(tmpservertimestampfile)
			finally:
				if self.rsync_initial_timeout:
					portage.exception.AlarmSignal.unregister()
				try:
					os.unlink(tmpservertimestampfile)
				except OSError:
					pass
		except portage.exception.AlarmSignal:
			# timed out
			print('timed out')
			# With waitpid and WNOHANG, only check the
			# first element of the tuple since the second
			# element may vary (bug #337465).
			if pids and os.waitpid(pids[0], os.WNOHANG)[0] == 0:
				os.kill(pids[0], signal.SIGTERM)
				os.waitpid(pids[0], 0)
			# This is the same code rsync uses for timeout.
			exitcode = 30
		else:
			if exitcode != os.EX_OK:
				if exitcode & 0xff:
					exitcode = (exitcode & 0xff) << 8
				else:
					exitcode = exitcode >> 8

		if content:
			try:
				servertimestamp = time.mktime(time.strptime(
					content[0], TIMESTAMP_FORMAT))
			except (OverflowError, ValueError):
				pass
		del command, pids, content

		if exitcode == os.EX_OK:
			if (servertimestamp != 0) and (servertimestamp == timestamp):
				is_synced = True
				self.logger(self.xterm_titles,
					">>> Cancelling sync -- Already current.")
				print()
				print(">>>")
				print(">>> Timestamps on the server and in the local repository are the same.")
				print(">>> Cancelling all further sync action. You are already up to date.")
				print(">>>")
				print(">>> In order to force sync, remove '%s'." % self.servertimestampfile)
				print(">>>")
				print()
				return is_synced, exitcode, updatecache_flg
			elif (servertimestamp != 0) and (servertimestamp < timestamp):
				self.logger(self.xterm_titles,
					">>> Server out of date: %s" % syncuri)
				print()
				print(">>>")
				print(">>> SERVER OUT OF DATE: %s" % syncuri)
				print(">>>")
				print(">>> In order to force sync, remove '%s'." % self.servertimestampfile)
				print(">>>")
				print()
				exitcode = SERVER_OUT_OF_DATE
			elif (servertimestamp == 0) or (servertimestamp > timestamp):
				# actual sync
				command = rsynccommand[:]
				submodule_paths = self._get_submodule_paths()
				if submodule_paths:
					# The only way to select multiple directories to
					# sync, without calling rsync multiple times, is
					# to use --relative.
					command.append("--relative")
					for path in submodule_paths:
						# /./ is special syntax supported with the
						# rsync --relative option.
						command.append(syncuri + "/./" + path)
					command.append(self.repo.location)
				else:
					command.extend([syncuri + "/", self.repo.location])

				exitcode = None
				try:
					exitcode = portage.process.spawn(command,
						**self.spawn_kwargs)
				finally:
					if exitcode is None:
						# interrupted
						exitcode = 128 + signal.SIGINT

					#   0	Success
					#   1	Syntax or usage error
					#   2	Protocol incompatibility
					#   5	Error starting client-server protocol
					#  35	Timeout waiting for daemon connection
					if exitcode not in (0, 1, 2, 5, 35):
						# If the exit code is not among those listed above,
						# then we may have a partial/inconsistent sync
						# state, so our previously read timestamp as well
						# as the corresponding file can no longer be
						# trusted.
						timestamp = 0
						try:
							os.unlink(self.servertimestampfile)
						except OSError:
							pass
					else:
						updatecache_flg = True

				if exitcode in [0,1,3,4,11,14,20,21]:
					is_synced = True
		elif exitcode in [1,3,4,11,14,20,21]:
			is_synced = True
		else:
			# Code 2 indicates protocol incompatibility, which is expected
			# for servers with protocol < 29 that don't support
			# --prune-empty-directories.  Retry for a server that supports
			# at least rsync protocol version 29 (>=rsync-2.6.4).
			pass
		return is_synced, exitcode, updatecache_flg
