# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Eclasses plug-in module for repoman.
Performs an live and ruby eclass checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'eclasses',
	'description': doc,
	'provides':{
		'live-module': {
			'name': "live",
			'sourcefile': "live",
			'class': "LiveEclassChecks",
			'description': doc,
			'functions': ['check'],
			'func_kwargs': {
			},
			'mod_kwargs': ['qatracker', 'repo_metadata', 'repo_settings',
			],
			'func_kwargs': {
				'ebuild': (None, None),
				'pkg': (None, None),
				'xpkg': (None, None),
				'y_ebuild': (None, None),
			},
			'module_runsIn': ['ebuilds'],
		},
		'ruby-module': {
			'name': "ruby",
			'sourcefile': "ruby",
			'class': "RubyEclassChecks",
			'description': doc,
			'functions': ['check'],
			'func_kwargs': {
			},
			'mod_kwargs': ['qatracker', 'repo_settings'
			],
			'func_kwargs': {
				'ebuild': (None, None),
				'pkg': (None, None),
			},
			'module_runsIn': ['ebuilds'],
		},
	},
	'version': 1,
}
