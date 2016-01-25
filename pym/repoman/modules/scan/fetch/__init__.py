# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """fetches plug-in module for repoman.
Performs fetch related checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'fetches',
	'description': doc,
	'provides':{
		'fetches-module': {
			'name': "fetches",
			'sourcefile': "fetches",
			'class': "FetchChecks",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
		},
	}
}

