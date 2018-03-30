# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Patches plug-in module for repoman LineChecks.
Performs PATCHES variable checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'patches-check': {
			'name': "patches",
			'sourcefile': "patches",
			'class': "EbuildPatches",
			'description': doc,
		},
	},
	'version': 1,
}

