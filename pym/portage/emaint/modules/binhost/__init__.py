# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Scan and generate metadata indexes for binary packages.
"""


module_spec = {
	'name': 'binhost',
	'description': __doc__,
	'provides':{
		'module1': {
			'name': "binhost",
			'class': "BinhostHandler",
			'description': __doc__,
			'functions': ['check', 'fix'],
			'func_desc': {}
			}
		}
	}
