# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Mirrors plug-in module for repoman.
Performs third party mirrors checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'mirrors',
	'description': doc,
	'provides':{
		'mirrors-module': {
			'name': "thirdpartymirrors",
			'sourcefile': "thirdpartymirrors",
			'class': "ThirdPartyMirrors",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
		},
	}
}

