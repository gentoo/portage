# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Useless plug-in module for repoman LineChecks.
Performs checks for useless operations on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'uselesscds-check': {
			'name': "uselesscds",
			'sourcefile': "cd",
			'class': "EbuildUselessCdS",
			'description': doc,
		},
		'uselessdodoc-check': {
			'name': "uselessdodoc",
			'sourcefile': "dodoc",
			'class': "EbuildUselessDodoc",
			'description': doc,
		},
	},
	'version': 1,
}
