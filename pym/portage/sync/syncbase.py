# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

'''
Base class for performing sync operations.
This class contains common initialization code and functions.
'''


import logging
import os

import portage
from portage.util import writemsg_level
from . import _SUBMODULE_PATH_MAP

class SyncBase(object):
	'''Base Sync class for subclassing'''

	short_desc = "Perform sync operations on repositories"

	@staticmethod
	def name():
		return "BlankSync"


	def can_progressbar(self, func):
		return False


	def __init__(self, bin_command, bin_pkg):
		self.options = None
		self.settings = None
		self.logger = None
		self.repo = None
		self.xterm_titles = None
		self.spawn_kwargs = None
		self.bin_command = None
		self._bin_command = bin_command
		self.bin_pkg = bin_pkg
		if bin_command:
			self.bin_command = portage.process.find_binary(bin_command)


	@property
	def has_bin(self):
		'''Checks for existance of the external binary.

		MUST only be called after _kwargs() has set the logger
		'''
		if self.bin_command is None:
			msg = ["Command not found: %s" % self._bin_command,
			"Type \"emerge %s\" to enable %s support."
			% (self.bin_pkg, self._bin_command)]
			for l in msg:
				writemsg_level("!!! %s\n" % l,
					level=logging.ERROR, noiselevel=-1)
			return False
		return True


	def _kwargs(self, kwargs):
		'''Sets internal variables from kwargs'''
		self.options = kwargs.get('options', {})
		self.settings = self.options.get('settings', None)
		self.logger = self.options.get('logger', None)
		self.repo = self.options.get('repo', None)
		self.xterm_titles = self.options.get('xterm_titles', False)
		self.spawn_kwargs = self.options.get('spawn_kwargs', None)


	def exists(self, **kwargs):
		'''Tests whether the repo actually exists'''
		if kwargs:
			self._kwargs(kwargs)
		elif not self.repo:
			return False
		if not os.path.exists(self.repo.location):
			return False
		return True


	def sync(self, **kwargs):
		'''Sync the repository'''
		raise NotImplementedError


	def post_sync(self, portdb, location, emerge_config):
		'''repo.sync_type == "Blank":
		# NOTE: Do this after reloading the config, in case
		# it did not exist prior to sync, so that the config
		# and portdb properly account for its existence.
		'''
		pass


	def _get_submodule_paths(self):
		paths = []
		emerge_config = self.options.get('emerge_config')
		if emerge_config is not None:
			for name in emerge_config.opts.get('--sync-submodule', []):
				paths.extend(_SUBMODULE_PATH_MAP[name])
		return tuple(paths)


class NewBase(SyncBase):
	'''Subclasses Syncbase adding a new() and runs it
	instead of update() if the repository does not exist()'''


	def __init__(self, bin_command, bin_pkg):
		SyncBase.__init__(self, bin_command, bin_pkg)


	def sync(self, **kwargs):
		'''Sync the repository'''
		if kwargs:
			self._kwargs(kwargs)

		if not self.has_bin:
			return (1, False)

		if not self.exists():
			return self.new()
		return self.update()


	def new(self, **kwargs):
		'''Do the initial download and install of the repository'''
		raise NotImplementedError


	def update(self):
		'''Update existing repository
		'''
		raise NotImplementedError
