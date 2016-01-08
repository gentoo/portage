# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Keywords plug-in module for repoman.
Performs keywords checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'keywords',
	'description': doc,
	'provides':{
		'keywords-module': {
			'name': "keywords",
			'sourcefile': "keywords",
			'class': "KeywordChecks",
			'description': doc,
			'functions': ['prepare', 'check'],
			'func_desc': {
			},
		},
	}
}

