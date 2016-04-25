# Copyright 2015-2016 Gentoo Foundation
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
			'mod_kwargs': ['repo_settings', 'qatracker', 'options', 'metadata_dtd',
			],
			'func_kwargs': {
				'checkdir': (None, None),
				'checkdirlist': (None, None),
				'muselist': ('Future', 'set'),
				'repolevel': (None, None),
				'xpkg': (None, None),
			},
		},
		'ebuild-metadata': {
			'name': "ebuild_metadata",
			'sourcefile': "ebuild_metadata",
			'class': "EbuildMetadata",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker',
			],
			'func_kwargs': {
				'catdir': (None, None),
				'ebuild': (None, None),
				'live_ebuild': (None, None),
				'xpkg': (None, None),
				'y_ebuild': (None, None),
			},
		},
		'description-metadata': {
			'name': "description",
			'sourcefile': "description",
			'class': "DescriptionChecks",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker',
			],
			'func_kwargs': {
				'ebuild': (None, None),
				'pkg': ('Future', 'UNSET'),
			},
		},
		'license-metadata': {
			'name': "license",
			'sourcefile': "license",
			'class': "LicenseChecks",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker', 'repo_metadata',
			],
			'func_kwargs': {
				'badlicsyntax': (None, None),
				'ebuild': (None, None),
				'xpkg': (None, None),
				'y_ebuild': (None, None),
			},
		},
		'restrict-metadata': {
			'name': "restrict",
			'sourcefile': "restrict",
			'class': "RestrictChecks",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker',
			],
			'func_kwargs': {
				'ebuild': (None, None),
				'xpkg': (None, None),
				'y_ebuild': (None, None),
			},
		},
		'unused-metadata': {
			'name': "unused",
			'sourcefile': "unused",
			'class': "UnusedCheck",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker',
			],
			'func_kwargs': {
				'muselist': (None, None),
				'used_useflags': (None, None),
				'validity_future': (None, None),
				'xpkg': (None, None),
			},
		},
	}
}

