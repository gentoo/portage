# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Do plug-in module for repoman LineChecks.
Performs do* checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'nonrelative-check': {
			'name': "dosym",
			'sourcefile': "dosym",
			'class': "EbuildNonRelativeDosym",
			'description': doc,
		},
	},
	'version': 1,
}
