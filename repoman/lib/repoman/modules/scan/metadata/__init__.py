# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Metadata plug-in module for repoman.
Performs metadata checks on packages."""
__doc__ = doc[:]


module_spec = {
	'name': 'metadata',
	'description': doc,
	'provides':{
		'pkg-metadata': {
			'name': "pkgmetadata",
			'sourcefile': "pkgmetadata",
			'class': "PkgMetadata",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['repo_settings', 'qatracker', 'options',
				'metadata_xsd', 'uselist',
			],
			'func_kwargs': {
				'checkdir': (None, None),
				'checkdirlist': (None, None),
				'ebuild': (None, None),
				'pkg': (None, None),
				'repolevel': (None, None),
				'validity_future': (None, None),
				'xpkg': (None, None),
				'y_ebuild': (None, None),
			},
			'module_runsIn': ['pkgs', 'ebuilds', 'final'],
		},
		'ebuild-metadata': {
			'name': "ebuild_metadata",
			'sourcefile': "ebuild_metadata",
			'class': "EbuildMetadata",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker', 'repo_settings',
			],
			'func_kwargs': {
				'catdir': (None, None),
				'ebuild': (None, None),
				'xpkg': (None, None),
				'y_ebuild': (None, None),
			},
			'module_runsIn': ['ebuilds'],
		},
		'description-metadata': {
			'name': "description",
			'sourcefile': "description",
			'class': "DescriptionChecks",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker', 'repo_settings'
			],
			'func_kwargs': {
				'ebuild': (None, None),
				'pkg': ('Future', 'UNSET'),
			},
			'module_runsIn': ['ebuilds'],
		},
		'restrict-metadata': {
			'name': "restrict",
			'sourcefile': "restrict",
			'class': "RestrictChecks",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker', 'repo_settings'
			],
			'func_kwargs': {
				'ebuild': (None, None),
				'xpkg': (None, None),
				'y_ebuild': (None, None),
			},
			'module_runsIn': ['ebuilds'],
		},
	},
	'version': 1,
}
