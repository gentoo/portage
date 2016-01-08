# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Ebuild plug-in module for repoman.
Performs an IsEbuild check on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'ebuild',
	'description': doc,
	'provides':{
		'ebuild-module': {
			'name': "isebuild",
			'sourcefile': "isebuild",
			'class': "IsEbuild",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
		},
	}
}

