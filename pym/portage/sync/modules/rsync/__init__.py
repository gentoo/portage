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
			'validate_config': CheckSyncConfig,
			}
		}
	}
