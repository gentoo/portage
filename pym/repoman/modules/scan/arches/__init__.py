# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Arches plug-in module for repoman.
Performs archs checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'arches',
	'description': doc,
	'provides':{
		'archs-module': {
			'name': "arches",
			'sourcefile': "arches",
			'class': "ArchChecks",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['options', 'repo_settings', 'profiles'
			],
			'func_kwargs': {'ebuild': None,
			},
		},
	}
}

