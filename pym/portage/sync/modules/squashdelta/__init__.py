#	vim:fileencoding=utf-8:noet
# (c) 2015 Michał Górny <mgorny@gentoo.org>
# Distributed under the terms of the GNU General Public License v2

from portage.sync.config_checks import CheckSyncConfig


DEFAULT_CACHE_LOCATION = '/var/cache/portage/squashfs'


class CheckSquashDeltaConfig(CheckSyncConfig):
	def __init__(self, repo, logger):
		CheckSyncConfig.__init__(self, repo, logger)
		self.checks.append('check_cache_location')

	def check_cache_location(self):
		# TODO: make it configurable when Portage is fixed to support
		# arbitrary config variables
		pass


module_spec = {
	'name': 'squashdelta',
	'description': 'Syncing SquashFS images using SquashDeltas',
	'provides': {
		'squashdelta-module': {
			'name': "squashdelta",
			'class': "SquashDeltaSync",
			'description': 'Syncing SquashFS images using SquashDeltas',
			'functions': ['sync'],
			'func_desc': {
				'sync': 'Performs the sync of the repository',
			},
			'validate_config': CheckSquashDeltaConfig,
		}
	}
}
