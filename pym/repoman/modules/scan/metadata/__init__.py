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
		},
		'ebuild-metadata': {
			'name': "ebuild_metadata",
			'sourcefile': "ebuild_metadata",
			'class': "EbuildMetadata",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
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
		},
		'license-metadata': {
			'name': "license",
			'sourcefile': "license",
			'class': "LicenseChecks",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
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
		},
		'unused-metadata': {
			'name': "unused",
			'sourcefile': "unused",
			'class': "UnusedCheck",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
		},
	}
}

