# Copyright 2005-2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging
import subprocess

import portage
from portage import os
from portage.util import writemsg_level, shlex_split
from portage.output import create_color_func
good = create_color_func("GOOD")
bad = create_color_func("BAD")
warn = create_color_func("WARN")
from portage.sync.syncbase import NewBase


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
		try:
			if not os.path.exists(self.repo.location):
				os.makedirs(self.repo.location)
				self.logger(self.xterm_titles,
					'Created new directory %s' % self.repo.location)
		except IOError:
			return (1, False)

		sync_uri = self.repo.sync_uri
		if sync_uri.startswith("file://"):
			sync_uri = sync_uri[6:]

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
		return (os.EX_OK, True)


	def update(self):
		''' Update existing git repository, and ignore the syncuri. We are
		going to trust the user and assume that the user is in the branch
		that he/she wants updated. We'll let the user manage branches with
		git directly.
		'''

		git_cmd_opts = ""
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
		git_cmd = "%s pull%s" % (self.bin_command, git_cmd_opts)
		writemsg_level(git_cmd + "\n")

		rev_cmd = [self.bin_command, "rev-list", "--max-count=1", "HEAD"]
		previous_rev = subprocess.check_output(rev_cmd,
			cwd=portage._unicode_encode(self.repo.location))

		exitcode = portage.process.spawn_bash("cd %s ; exec %s" % (
				portage._shell_quote(self.repo.location), git_cmd),
			**self.spawn_kwargs)
		if exitcode != os.EX_OK:
			msg = "!!! git pull error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)

		current_rev = subprocess.check_output(rev_cmd,
			cwd=portage._unicode_encode(self.repo.location))

		return (os.EX_OK, current_rev != previous_rev)

	def retrieve_head(self, **kwargs):
		'''Get information about the head commit'''
		if kwargs:
			self._kwargs(kwargs)
		rev_cmd = [self.bin_command, "rev-list", "--max-count=1", "HEAD"]
		try:
			ret = (os.EX_OK,
				portage._unicode_decode(subprocess.check_output(rev_cmd,
				cwd=portage._unicode_encode(self.repo.location))))
		except subprocess.CalledProcessError:
			ret = (1, False)
		return ret
