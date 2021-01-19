# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Depend plug-in module for repoman.
Performs Dependency checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'depend',
	'description': doc,
	'provides':{
		'profile-module': {
			'name': "profile",
			'sourcefile': "profile",
			'class': "ProfileDependsChecks",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker', 'portdb', 'profiles', 'options',
				'repo_metadata', 'repo_settings', 'include_arches',
				'include_profiles', 'caches',
				'repoman_incrementals', 'env', 'have', 'dev_keywords'
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
