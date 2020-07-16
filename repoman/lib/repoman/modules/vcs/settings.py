'''
Repoman VCSSettings modules
'''

from __future__ import print_function

import logging
import sys

from portage.output import red
from repoman.modules.vcs import module_controller, module_names
from repoman.modules.vcs.vcs import FindVCS
from repoman.qa_tracker import QATracker


class VCSSettings(object):
	'''Holds various VCS settings'''

	def __init__(self, options=None, repoman_settings=None, repo_settings=None):
		'''Class init function

		@param options: the run time cli options
		@param repoman_settings: portage.config settings instance
		@param repo_settings: RepoSettings instance
		'''
		self.options = options
		self.repoman_settings = repoman_settings
		self.repo_settings = repo_settings
		if options.vcs:
			if options.vcs in module_names:
				self.vcs = options.vcs
			else:
				self.vcs = None
		else:
			vcses = FindVCS()
			if len(vcses) > 1:
				print(red(
					'*** Ambiguous workdir -- more than one VCS found'
					' at the same depth: %s.' % ', '.join(vcses)))
				print(red(
					'*** Please either clean up your workdir'
					' or specify --vcs option.'))
				sys.exit(1)
			elif vcses:
				self.vcs = vcses[0]
			else:
				self.vcs = None

		if options.if_modified == "y" and self.vcs is None:
			logging.info(
				"Not in a version controlled repository; "
				"disabling --if-modified.")
			options.if_modified = "n"

		# initialize our instance placeholders
		self._status = None
		self._changes = None
		# get our vcs plugin controller and available module names
		self.module_controller = module_controller
		self.module_names = module_names

		# Disable copyright/mtime check if vcs does not preserve mtime (bug #324075).
		if str(self.vcs) in self.module_controller.parents:
			self.vcs_preserves_mtime = module_controller.modules[
				"%s_status" % self.vcs]['vcs_preserves_mtime']
		else:
			self.vcs_preserves_mtime = False
			logging.error("VCSSettings: Unknown VCS type: %s", self.vcs)
			logging.error("Available modules: %s", module_controller.parents)

		self.needs_keyword_expansion = module_controller.modules[
				"%s_status" % self.vcs]['needs_keyword_expansion']
		self.vcs_local_opts = repoman_settings.get(
			"REPOMAN_VCS_LOCAL_OPTS", "").split()
		self.vcs_global_opts = repoman_settings.get(
			"REPOMAN_VCS_GLOBAL_OPTS")
		if self.vcs_global_opts is None:
			if self.vcs in ('cvs', 'svn'):
				self.vcs_global_opts = "-q"
			else:
				self.vcs_global_opts = ""
		self.vcs_global_opts = self.vcs_global_opts.split()

		if options.mode == 'commit' and not options.pretend and not self.vcs:
			logging.info(
				"Not in a version controlled repository; "
				"enabling pretend mode.")
			options.pretend = True
		self.qatracker = QATracker()
		self.eadded = []

	@property
	def status(self):
		'''Initializes and returns the class instance
		of the vcs's Status class'''
		if not self._status:
			status = self.module_controller.get_class('%s_status' % self.vcs)
			self._status = status(self.qatracker, self.eadded)
		return self._status

	@property
	def changes(self):
		'''Initializes and returns the class instance
		of the vcs's Changes class'''
		if not self._changes:
			changes = self.module_controller.get_class('%s_changes' % self.vcs)
			self._changes = changes(self.options, self.repo_settings)
		return self._changes
