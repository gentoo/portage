# Copyright 2015-2016 Gentoo Foundation
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
			'func_kwargs': {
			},
		},
	}
}

