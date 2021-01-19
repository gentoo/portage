# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Use plug-in module for repoman LineChecks.
Performs Built-With-Use checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'builtwith-check': {
			'name': "builtwith",
			'sourcefile': "builtwith",
			'class': "BuiltWithUse",
			'description': doc,
		},
	},
	'version': 1,
}
