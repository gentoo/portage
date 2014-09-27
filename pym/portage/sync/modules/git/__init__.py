# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Git plug-in module for portage.
Performs a git pull on repositories."""
__doc__ = doc[:]

from portage.sync.config_checks import CheckSyncConfig


module_spec = {
	'name': 'git',
	'description': doc,
	'provides':{
		'git-module': {
			'name': "git",
			'class': "GitSync",
			'description': doc,
			'functions': ['sync', 'new', 'exists'],
			'func_desc': {
				'sync': 'Performs a git pull on the repository',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean of whether the specified dir ' +
					'exists and is a valid Git repository',
			},
			'validate_config': CheckSyncConfig,
		}
	}
}
