# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """CVS plug-in module for portage.
Performs a cvs up on repositories."""
__doc__ = doc[:]

from portage.localization import _
from portage.sync.config_checks import CheckSyncConfig
from portage.util import writemsg_level


class CheckCVSConfig(CheckSyncConfig):

	def __init__(self, repo, logger):
		CheckSyncConfig.__init__(self, repo, logger)
		self.checks.append('check_cvs_repo')


	def check_cvs_repo(self):
		if self.repo.module_specific_options.get('sync-cvs-repo') is None:
			writemsg_level("!!! %s\n" %
				_("Repository '%s' has sync-type=cvs, but is missing sync-cvs-repo attribute")
				% self.repo.name, level=self.logger.ERROR, noiselevel=-1)


module_spec = {
	'name': 'cvs',
	'description': doc,
	'provides':{
		'cvs-module': {
			'name': "cvs",
			'sourcefile': "cvs",
			'class': "CVSSync",
			'description': doc,
			'functions': ['sync', 'new', 'exists'],
			'func_desc': {
				'sync': 'Performs a cvs up on the repository',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean of whether the specified dir ' +
					'exists and is a valid CVS repository',
			},
			'validate_config': CheckCVSConfig,
			'module_specific_options': ("sync-cvs-repo",),
		}
	}
}
