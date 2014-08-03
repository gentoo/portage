# Copyright 2005-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Scan for failed merges and fix them."""


module_spec = {
	'name': 'merges',
	'description': __doc__,
	'provides': {
		'merges': {
			'name': "merges",
			'class': "MergesHandler",
			'description': __doc__,
			'functions': ['check', 'fix', 'purge'],
			'func_desc': {
				'purge': {
					'short': '-P', 'long': '--purge-tracker',
					'help': 'Removes the list of previously failed merges.' +
							' WARNING: Only use this option if you plan on' +
							' manually fixing them or do not want them'
							' re-installed.',
					'status': "Removing %s",
					'action': 'store_true',
					'func': 'purge'
				}
			}
		}
	}
}
