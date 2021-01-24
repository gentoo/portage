# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Ebuild plug-in module for repoman.
Performs an IsEbuild check on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'manifest',
	'description': doc,
	'provides':{
		'manifest-module': {
			'name': "manifests",
			'sourcefile': "manifests",
			'class': "Manifests",
			'description': doc,
			'functions': ['check', 'create_manifest', 'digest_check'],
			'func_desc': {
			},
			'mod_kwargs': ['options', 'portdb', 'qatracker', 'repo_settings',
			],
			'func_kwargs': {
				'checkdir': (None, None),
				'xpkg': (None, None),
			},
			'module_runsIn': ['pkgs'],
		},
	},
	'version': 1,
}
