# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

'''
Base class for performing repos.conf sync variables checks.
This class contains common checks code and functions.

For additional checks or other customizations,
subclass it adding and/or overriding classes as needed.
'''

import logging

from portage.localization import _
from portage.util import writemsg_level


def check_type(repo, logger, module_names):
	if repo.sync_uri is not None and repo.sync_type is None:
		writemsg_level("!!! %s\n" %
			_("Repository '%s' has sync-uri attribute, but is missing sync-type attribute")
			% repo.name, level=logger.ERROR, noiselevel=-1)
		return False
	if repo.sync_type not in module_names + [None]:
		writemsg_level("!!! %s\n" %
			_("Repository '%s' has sync-type attribute set to unsupported value: '%s'")
			% (repo.name, repo.sync_type),
			level=logger.ERROR, noiselevel=-1)
		writemsg_level("!!! %s\n" %
			_("Installed sync-types are: '%s'")
			% (str(module_names)),
			level=logger.ERROR, noiselevel=-1)
		return False
	return True


class CheckSyncConfig:
	'''Base repos.conf settings checks class'''

	def __init__(self, repo=None, logger=None):
		'''Class init function

		@param logger: optional logging instance,
			defaults to logging module
		'''
		self.logger = logger or logging
		self.repo = repo
		self.checks = ['check_uri', 'check_auto_sync']


	def repo_checks(self):
		'''Perform all checks available'''
		for check in self.checks:
			getattr(self, check)()


	def check_uri(self):
		'''Check the sync_uri setting'''
		if self.repo.sync_uri is None:
			writemsg_level("!!! %s\n" % _("Repository '%s' has sync-type attribute, but is missing sync-uri attribute")
				% self.repo.name, level=self.logger.ERROR, noiselevel=-1)


	def check_auto_sync(self):
		'''Check the auto_sync setting'''
		if self.repo.auto_sync is None:
			writemsg_level("!!! %s\n" % _("Repository '%s' is missing auto_sync attribute")
				% self.repo.name, level=self.logger.ERROR, noiselevel=-1)
		elif self.repo.auto_sync.lower() not in ["yes", "true", "no", "false"]:
			writemsg_level("!!! %s\n" % _("Repository '%s' auto_sync attribute must be one of: %s")
				% (self.repo.name, '{yes, true, no, false}'),
				level=self.logger.ERROR, noiselevel=-1)
