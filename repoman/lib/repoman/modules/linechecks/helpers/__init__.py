# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Helpers plug-in module for repoman LineChecks.
Performs variable helpers checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'nooffset-check': {
			'name': "nooffset",
			'sourcefile': "offset",
			'class': "NoOffsetWithHelpers",
			'description': doc,
		},
	},
	'version': 1,
}
