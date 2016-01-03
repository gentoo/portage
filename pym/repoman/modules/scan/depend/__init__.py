# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Depend plug-in module for repoman.
Performs Dependency checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'depend',
	'description': doc,
	'provides':{
		'depend-module': {
			'name': "depend",
			'sourcefile': "depend",
			'class': "DependChecks",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
		},
	}
}

