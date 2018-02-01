# Copyright 2014-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Rsync plug-in module for portage.
   Performs rsync transfers on repositories."""
__doc__ = doc[:]

from portage.sync.config_checks import CheckSyncConfig


module_spec = {
	'name': 'rsync',
	'description': doc,
	'provides':{
		'rsync-module': {
			'name': "rsync",
			'sourcefile': "rsync",
			'class': "RsyncSync",
			'description': doc,
			'functions': ['sync', 'new', 'exists', 'retrieve_head'],
			'func_desc': {
				'sync': 'Performs rsync transfers on the repository',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean if the specified directory exists',
				'retrieve_head': 'Returns the head commit based on metadata/timestamp.commit',
				},
			'validate_config': CheckSyncConfig,
			'module_specific_options': (
				'sync-rsync-extra-opts',
				'sync-rsync-vcs-ignore',
				'sync-rsync-verify-jobs',
				'sync-rsync-verify-max-age',
				'sync-rsync-verify-metamanifest',
				),
			}
		}
	}
