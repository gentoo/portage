# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""CVS plug-in module for portage.
Performs a cvs up on repositories
"""


from portage.localization import _
from portage.sync.config_checks import CheckSyncConfig
from portage.util import writemsg_level


class CheckCVSConfig(CheckSyncConfig):

	def __init__(self, logger):
		CheckSyncConfig.__init__(self, logger)
		self.checks.append('check_cvs_repo')


	def check_cvs_repo(self):
		if self.repo.sync_cvs_repo is None:
			writemsg_level("!!! %s\n" %
				_("Repository '%s' has sync-type=cvs, but is missing sync-cvs-repo attribute")
				% self.repo.name, level=self.logger.ERROR, noiselevel=-1)


module_spec = {
	'name': 'cvs',
	'description': __doc__,
	'provides':{
		'cvs-module': {
			'name': "cvs",
			'class': "CVSSync",
			'description': __doc__,
			'functions': ['sync', 'new', 'exists'],
			'func_desc': {
				'sync': 'Performs a cvs up on the repository',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean of whether the specified dir ' +
					'exists and is a valid CVS repository',
			},
			'func_parameters': {
				'kwargs': {
					'type': dict,
					'description': 'Standard python **kwargs parameter format' +
						'Please refer to the sync modules specs at ' +
						'"https://wiki.gentoo.org:Project:Portage" for details',
					'required-keys': ['options', 'settings', 'logger', 'repo',
						'xterm_titles', 'spawn_kwargs'],
				},
			},
			'validate_config': CheckCVSConfig,
		}
	}
}
