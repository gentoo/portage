# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Git plug-in module for portage.
Performs a git pull on repositories."""
__doc__ = doc[:]

from portage.localization import _
from portage.sync.config_checks import CheckSyncConfig
from portage.util import writemsg_level


class CheckGitConfig(CheckSyncConfig):
	def __init__(self, repo, logger):
		CheckSyncConfig.__init__(self, repo, logger)
		self.checks.append('check_depth')

	def check_depth(self):
		d = self.repo.sync_depth
		# default
		self.repo.sync_depth = 1

		if d is not None:
			try:
				d = int(d)
			except ValueError:
				writemsg_level("!!! %s\n" %
					_("sync-depth value is not a number: '%s'")
					% (d),
					level=self.logger.ERROR, noiselevel=-1)
			else:
				if d == 0:
					d = None
				self.repo.sync_depth = d


module_spec = {
	'name': 'git',
	'description': doc,
	'provides':{
		'git-module': {
			'name': "git",
			'sourcefile': "git",
			'class': "GitSync",
			'description': doc,
			'functions': ['sync', 'new', 'exists'],
			'func_desc': {
				'sync': 'Performs a git pull on the repository',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean of whether the specified dir ' +
					'exists and is a valid Git repository',
			},
			'validate_config': CheckGitConfig,
			'module_specific_options': (
				'sync-git-clone-extra-opts',
				'sync-git-pull-extra-opts',
				),
		}
	}
}
