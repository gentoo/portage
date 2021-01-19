# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Eapi plug-in module for repoman.
Performs an IsEbuild check on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'eapi',
	'description': doc,
	'provides':{
		'live-module': {
			'name': "eapi",
			'sourcefile': "eapi",
			'class': "EAPIChecks",
			'description': doc,
			'functions': ['check'],
			'func_kwargs': {
			},
			'mod_kwargs': ['qatracker', 'repo_settings'
			],
			'func_kwargs': {
				'ebuild': (None, None),
			},
			'module_runsIn': ['ebuilds'],
		},
	},
	'version': 1,
}
