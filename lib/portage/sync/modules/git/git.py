# Copyright 2005-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import io
import logging
import subprocess

import portage
from portage import os
from portage.util import writemsg_level, shlex_split
from portage.util.futures import asyncio
from portage.output import create_color_func, EOutput
good = create_color_func("GOOD")
bad = create_color_func("BAD")
warn = create_color_func("WARN")
from portage.sync.syncbase import NewBase

try:
	from gemato.exceptions import GematoException
	import gemato.openpgp
except ImportError:
	gemato = None


class GitSync(NewBase):
	'''Git sync class'''

	short_desc = "Perform sync operations on git based repositories"

	@staticmethod
	def name():
		return "GitSync"


	def __init__(self):
		NewBase.__init__(self, "git", portage.const.GIT_PACKAGE_ATOM)


	def exists(self, **kwargs):
		'''Tests whether the repo actually exists'''
		return os.path.exists(os.path.join(self.repo.location, '.git'))


	def new(self, **kwargs):
		'''Do the initial clone of the repository'''
		if kwargs:
			self._kwargs(kwargs)
		if not self.has_bin:
			return (1, False)
		try:
			if not os.path.exists(self.repo.location):
				os.makedirs(self.repo.location)
				self.logger(self.xterm_titles,
					'Created new directory %s' % self.repo.location)
		except IOError:
			return (1, False)

		sync_uri = self.repo.sync_uri
		if sync_uri.startswith("file://"):
			sync_uri = sync_uri[7:]

		git_cmd_opts = ""
		if self.repo.module_specific_options.get('sync-git-env'):
			shlexed_env = shlex_split(self.repo.module_specific_options['sync-git-env'])
			env = dict((k, v) for k, _, v in (assignment.partition('=') for assignment in shlexed_env) if k)
			self.spawn_kwargs['env'].update(env)

		if self.repo.module_specific_options.get('sync-git-clone-env'):
			shlexed_env = shlex_split(self.repo.module_specific_options['sync-git-clone-env'])
			clone_env = dict((k, v) for k, _, v in (assignment.partition('=') for assignment in shlexed_env) if k)
			self.spawn_kwargs['env'].update(clone_env)

		if self.settings.get("PORTAGE_QUIET") == "1":
			git_cmd_opts += " --quiet"
		if self.repo.clone_depth is not None:
			if self.repo.clone_depth != 0:
				git_cmd_opts += " --depth %d" % self.repo.clone_depth
		elif self.repo.sync_depth is not None:
			if self.repo.sync_depth != 0:
				git_cmd_opts += " --depth %d" % self.repo.sync_depth
		else:
			# default
			git_cmd_opts += " --depth 1"

		if self.repo.module_specific_options.get('sync-git-clone-extra-opts'):
			git_cmd_opts += " %s" % self.repo.module_specific_options['sync-git-clone-extra-opts']
		git_cmd = "%s clone%s %s ." % (self.bin_command, git_cmd_opts,
			portage._shell_quote(sync_uri))
		writemsg_level(git_cmd + "\n")

		exitcode = portage.process.spawn_bash("cd %s ; exec %s" % (
				portage._shell_quote(self.repo.location), git_cmd),
			**self.spawn_kwargs)
		if exitcode != os.EX_OK:
			msg = "!!! git clone error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)
		if not self.verify_head():
			return (1, False)
		return (os.EX_OK, True)


	def update(self):
		''' Update existing git repository, and ignore the syncuri. We are
		going to trust the user and assume that the user is in the branch
		that he/she wants updated. We'll let the user manage branches with
		git directly.
		'''
		if not self.has_bin:
			return (1, False)
		git_cmd_opts = ""
		quiet = self.settings.get("PORTAGE_QUIET") == "1"
		if self.repo.module_specific_options.get('sync-git-env'):
			shlexed_env = shlex_split(self.repo.module_specific_options['sync-git-env'])
			env = dict((k, v) for k, _, v in (assignment.partition('=') for assignment in shlexed_env) if k)
			self.spawn_kwargs['env'].update(env)

		if self.repo.module_specific_options.get('sync-git-pull-env'):
			shlexed_env = shlex_split(self.repo.module_specific_options['sync-git-pull-env'])
			pull_env = dict((k, v) for k, _, v in (assignment.partition('=') for assignment in shlexed_env) if k)
			self.spawn_kwargs['env'].update(pull_env)

		if self.settings.get("PORTAGE_QUIET") == "1":
			git_cmd_opts += " --quiet"
		if self.repo.module_specific_options.get('sync-git-pull-extra-opts'):
			git_cmd_opts += " %s" % self.repo.module_specific_options['sync-git-pull-extra-opts']

		try:
			remote_branch = portage._unicode_decode(
				subprocess.check_output([self.bin_command, 'rev-parse',
				'--abbrev-ref', '--symbolic-full-name', '@{upstream}'],
				cwd=portage._unicode_encode(self.repo.location))).rstrip('\n')
		except subprocess.CalledProcessError as e:
			msg = "!!! git rev-parse error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (e.returncode, False)

		shallow = self.repo.sync_depth is not None and self.repo.sync_depth != 0
		if shallow:
			git_cmd_opts += " --depth %d" % self.repo.sync_depth

			# For shallow fetch, unreachable objects may need to be pruned
			# manually, in order to prevent automatic git gc calls from
			# eventually failing (see bug 599008).
			gc_cmd = ['git', '-c', 'gc.autodetach=false', 'gc', '--auto']
			if quiet:
				gc_cmd.append('--quiet')
			exitcode = portage.process.spawn(gc_cmd,
				cwd=portage._unicode_encode(self.repo.location),
				**self.spawn_kwargs)
			if exitcode != os.EX_OK:
				msg = "!!! git gc error in %s" % self.repo.location
				self.logger(self.xterm_titles, msg)
				writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
				return (exitcode, False)

		git_cmd = "%s fetch %s%s" % (self.bin_command,
			remote_branch.partition('/')[0], git_cmd_opts)

		writemsg_level(git_cmd + "\n")

		rev_cmd = [self.bin_command, "rev-list", "--max-count=1", "HEAD"]
		previous_rev = subprocess.check_output(rev_cmd,
			cwd=portage._unicode_encode(self.repo.location))

		exitcode = portage.process.spawn_bash("cd %s ; exec %s" % (
				portage._shell_quote(self.repo.location), git_cmd),
			**self.spawn_kwargs)

		if exitcode != os.EX_OK:
			msg = "!!! git fetch error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)

		if not self.verify_head(revision='refs/remotes/%s' % remote_branch):
			return (1, False)

		if shallow:
			# Since the default merge strategy typically fails when
			# the depth is not unlimited, `git reset --merge`.
			merge_cmd = [self.bin_command, 'reset', '--merge']
		else:
			merge_cmd = [self.bin_command, 'merge']
		merge_cmd.append('refs/remotes/%s' % remote_branch)
		if quiet:
			merge_cmd.append('--quiet')
		exitcode = portage.process.spawn(merge_cmd,
			cwd=portage._unicode_encode(self.repo.location),
			**self.spawn_kwargs)

		if exitcode != os.EX_OK:
			msg = "!!! git merge error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)

		current_rev = subprocess.check_output(rev_cmd,
			cwd=portage._unicode_encode(self.repo.location))

		return (os.EX_OK, current_rev != previous_rev)

	def verify_head(self, revision='-1'):
		if (self.repo.module_specific_options.get(
				'sync-git-verify-commit-signature', 'false').lower() not in ('true', 'yes')):
			return True

		if self.repo.sync_openpgp_key_path is not None and gemato is None:
			writemsg_level("!!! Verifying against specified key requires gemato-14.5+ installed\n",
					level=logging.ERROR, noiselevel=-1)
			return False

		openpgp_env = self._get_openpgp_env(self.repo.sync_openpgp_key_path)

		try:
			out = EOutput()
			env = None
			if openpgp_env is not None and self.repo.sync_openpgp_key_path is not None:
				try:
					out.einfo('Using keys from %s' % (self.repo.sync_openpgp_key_path,))
					with io.open(self.repo.sync_openpgp_key_path, 'rb') as f:
						openpgp_env.import_key(f)
					self._refresh_keys(openpgp_env)
				except (GematoException, asyncio.TimeoutError) as e:
					writemsg_level("!!! Verification impossible due to keyring problem:\n%s\n"
							% (e,),
							level=logging.ERROR, noiselevel=-1)
					return False

				env = os.environ.copy()
				env['GNUPGHOME'] = openpgp_env.home

			rev_cmd = [self.bin_command, "log", "-n1", "--pretty=format:%G?", revision]
			try:
				status = (portage._unicode_decode(
					subprocess.check_output(rev_cmd,
						cwd=portage._unicode_encode(self.repo.location),
						env=env))
					.strip())
			except subprocess.CalledProcessError:
				return False

			if status == 'G':  # good signature is good
				out.einfo('Trusted signature found on top commit')
				return True
			if status == 'U':  # untrusted
				out.ewarn('Top commit signature is valid but not trusted')
				return True
			if status == 'B':
				expl = 'bad signature'
			elif status == 'X':
				expl = 'expired signature'
			elif status == 'Y':
				expl = 'expired key'
			elif status == 'R':
				expl = 'revoked key'
			elif status == 'E':
				expl = 'unable to verify signature (missing key?)'
			elif status == 'N':
				expl = 'no signature'
			else:
				expl = 'unknown issue'
			out.eerror('No valid signature found: %s' % (expl,))
			return False
		finally:
			if openpgp_env is not None:
				openpgp_env.close()

	def retrieve_head(self, **kwargs):
		'''Get information about the head commit'''
		if kwargs:
			self._kwargs(kwargs)
		if self.bin_command is None:
			# return quietly so that we don't pollute emerge --info output
			return (1, False)
		rev_cmd = [self.bin_command, "rev-list", "--max-count=1", "HEAD"]
		try:
			ret = (os.EX_OK,
				portage._unicode_decode(subprocess.check_output(rev_cmd,
				cwd=portage._unicode_encode(self.repo.location))))
		except subprocess.CalledProcessError:
			ret = (1, False)
		return ret
