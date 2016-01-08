# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Metadata plug-in module for repoman.
Performs metadata checks on packages."""
__doc__ = doc[:]


module_spec = {
	'name': 'metadata',
	'description': doc,
	'provides':{
		'metadata-module': {
			'name': "pkgmetadata",
			'sourcefile': "pkgmetadata",
			'class': "PkgMetadata",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
		},
	}
}

