# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """fetches plug-in module for repoman.
Performs fetch related checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'fetches',
	'description': doc,
	'provides':{
		'fetches-module': {
			'name': "fetches",
			'sourcefile': "fetches",
			'class': "FetchChecks",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['portdb', 'qatracker', 'repo_settings', 'vcs_settings',
			],
			'func_kwargs': {
				'changed': (None, None),
				'checkdir': (None, None),
				'checkdir_relative': (None, None),
				'ebuild': (None, None),
				'xpkg': (None, None),
			},
			'module_runsIn': ['pkgs', 'ebuilds'],
		},
	},
	'version': 1,
}
