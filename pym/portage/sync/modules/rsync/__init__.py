# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Rsync plug-in module for portage.
   Performs rsync transfers on repositories
"""


from portage.sync.config_checks import CheckSyncConfig


module_spec = {
	'name': 'rsync',
	'description': __doc__,
	'provides':{
		'rsync-module': {
			'name': "rsync",
			'class': "RsyncSync",
			'description': __doc__,
			'functions': ['sync', 'new', 'exists'],
			'func_desc': {
				'sync': 'Performs rsync transfers on the repository',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean if the specified directory exists',
				},
			'validate_config': CheckSyncConfig,
			}
		}
	}
