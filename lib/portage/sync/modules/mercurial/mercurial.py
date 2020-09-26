# Copyright 2018-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging
import subprocess

import portage
from portage import os
from portage.util import writemsg_level, shlex_split

from portage.sync.syncbase import NewBase


class MercurialSync(NewBase):
	"""Mercurial sync class"""

	short_desc = "Perform sync operations on mercurial based repositories"

	@staticmethod
	def name():
		return "MercurialSync"

	def __init__(self):
		NewBase.__init__(self, "hg", portage.const.HG_PACKAGE_ATOM)

	def exists(self, **kwargs):
		"""Tests whether the repo actually exists"""
		return os.path.exists(os.path.join(self.repo.location, ".hg"))

	def new(self, **kwargs):
		"""Do the initial clone of the repository"""
		if kwargs:
			self._kwargs(kwargs)
		try:
			if not os.path.exists(self.repo.location):
				os.makedirs(self.repo.location)
				self.logger(
					self.xterm_titles, "Created new directory %s" % self.repo.location
				)
		except IOError:
			return (1, False)

		sync_uri = self.repo.sync_uri
		if sync_uri.startswith("file://"):
			sync_uri = sync_uri[7:]

		hg_cmd_opts = ""
		if self.repo.module_specific_options.get("sync-mercurial-env"):
			shlexed_env = shlex_split(
				self.repo.module_specific_options["sync-mercurial-env"]
			)
			env = dict(
				(k, v)
				for k, _, v in (assignment.partition("=") for assignment in shlexed_env)
				if k
			)
			self.spawn_kwargs["env"].update(env)

		if self.repo.module_specific_options.get("sync-mercurial-clone-env"):
			shlexed_env = shlex_split(
				self.repo.module_specific_options["sync-mercurial-clone-env"]
			)
			clone_env = dict(
				(k, v)
				for k, _, v in (assignment.partition("=") for assignment in shlexed_env)
				if k
			)
			self.spawn_kwargs["env"].update(clone_env)

		if self.settings.get("PORTAGE_QUIET") == "1":
			hg_cmd_opts += " --quiet"
		if self.repo.module_specific_options.get("sync-mercurial-clone-extra-opts"):
			hg_cmd_opts += (
				" %s"
				% self.repo.module_specific_options["sync-mercurial-clone-extra-opts"]
			)
		hg_cmd = "%s clone%s %s ." % (
			self.bin_command,
			hg_cmd_opts,
			portage._shell_quote(sync_uri),
		)
		writemsg_level(hg_cmd + "\n")

		exitcode = portage.process.spawn(
			shlex_split(hg_cmd),
			cwd=portage._unicode_encode(self.repo.location),
			**self.spawn_kwargs
		)
		if exitcode != os.EX_OK:
			msg = "!!! hg clone error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)
		return (os.EX_OK, True)

	def update(self):
		"""Update existing mercurial repository, and ignore the syncuri. We are
		going to trust the user and assume that the user is in the branch
		that he/she wants updated. We'll let the user manage branches with
		hg directly.
		"""

		hg_cmd_opts = ""
		if self.repo.module_specific_options.get("sync-mercurial-env"):
			shlexed_env = shlex_split(
				self.repo.module_specific_options["sync-mercurial-env"]
			)
			env = dict(
				(k, v)
				for k, _, v in (assignment.partition("=") for assignment in shlexed_env)
				if k
			)
			self.spawn_kwargs["env"].update(env)

		if self.repo.module_specific_options.get("sync-mercurial-pull-env"):
			shlexed_env = shlex_split(
				self.repo.module_specific_options["sync-mercurial-pull-env"]
			)
			pull_env = dict(
				(k, v)
				for k, _, v in (assignment.partition("=") for assignment in shlexed_env)
				if k
			)
			self.spawn_kwargs["env"].update(pull_env)

		if self.settings.get("PORTAGE_QUIET") == "1":
			hg_cmd_opts += " --quiet"
		if self.repo.module_specific_options.get("sync-mercurial-pull-extra-opts"):
			hg_cmd_opts += (
				" %s"
				% self.repo.module_specific_options["sync-mercurial-pull-extra-opts"]
			)
		hg_cmd = "%s pull -u%s" % (self.bin_command, hg_cmd_opts)
		writemsg_level(hg_cmd + "\n")

		rev_cmd = [self.bin_command, "id", "--id", "--rev", "tip"]
		previous_rev = subprocess.check_output(
			rev_cmd, cwd=portage._unicode_encode(self.repo.location)
		)

		exitcode = portage.process.spawn(
			shlex_split(hg_cmd),
			cwd=portage._unicode_encode(self.repo.location),
			**self.spawn_kwargs
		)
		if exitcode != os.EX_OK:
			msg = "!!! hg pull error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)

		current_rev = subprocess.check_output(
			rev_cmd, cwd=portage._unicode_encode(self.repo.location)
		)

		return (os.EX_OK, current_rev != previous_rev)

	def retrieve_head(self, **kwargs):
		"""Get information about the head commit"""
		if kwargs:
			self._kwargs(kwargs)
		rev_cmd = [self.bin_command, "id", "--id", "--rev", "tip"]
		try:
			ret = (
				os.EX_OK,
				portage._unicode_decode(
					subprocess.check_output(
						rev_cmd, cwd=portage._unicode_encode(self.repo.location)
					)
				),
			)
		except subprocess.CalledProcessError:
			ret = (1, False)
		return ret
