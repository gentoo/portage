# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Ebuild plug-in module for repoman.
Performs an IsEbuild check on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'ebuild',
	'description': doc,
	'provides':{
		'ebuild-module': {
			'name': "ebuild",
			'sourcefile': "ebuild",
			'class': "Ebuild",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker', 'repo_settings', 'vcs_settings',
				'checks', 'portdb'
			],
			'func_kwargs': {
				'can_force': (None, None),
				'catdir': (None, None),
				'changed': (None, None),
				'changelog_modified': (None, None),
				'checkdir': (None, None),
				'checkdirlist': (None, None),
				'ebuild': ('Future', 'UNSET'),
				'pkg': ('Future', 'UNSET'),
				'pkgdir': (None, None),
				'pkgs': ('Future', 'dict'),
				'repolevel': (None, None),
				'validity_future': (None, None),
				'xpkg': (None, None),
				'y_ebuild': (None, None),
			},
			'module_runsIn': ['pkgs', 'ebuilds'],
		},
		'multicheck-module': {
			'name': "multicheck",
			'sourcefile': "multicheck",
			'class': "MultiCheck",
			'description': doc,
			'functions': ['check'],
			'func_kwargs': {
			},
			'mod_kwargs': ['qatracker', 'options', 'repo_settings', 'linechecks',
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
