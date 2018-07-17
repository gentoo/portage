# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Scan and generate metadata indexes for binary packages."""
__doc__ = doc


module_spec = {
	'name': 'binhost',
	'description': doc,
	'provides':{
		'module1': {
			'name': "binhost",
			'sourcefile': "binhost",
			'class': "BinhostHandler",
			'description': doc,
			'functions': ['check', 'fix'],
			'func_desc': {}
			}
		}
	}
