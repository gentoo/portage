# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Keywords plug-in module for repoman.
Performs keywords checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'keywords',
	'description': doc,
	'provides':{
		'keywords-module': {
			'name': "keywords",
			'sourcefile': "keywords",
			'class': "KeywordChecks",
			'description': doc,
			'functions': ['prepare', 'check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker', 'options', 'repo_metadata', 'profiles',
			],
			'func_kwargs': {
				'changed': (None, None),
				'ebuild': ('Future', 'UNSET'),
				'pkg': ('Future', 'UNSET'),
				'xpkg': None,
				'y_ebuild': (None, None),
			},
			'module_runsIn': ['pkgs', 'ebuilds', 'final'],
		},
	},
	'version': 1,
}
