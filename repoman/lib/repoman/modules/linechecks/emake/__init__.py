# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Emake plug-in module for repoman LineChecks.
Performs emake checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'paralleldisabled-check': {
			'name': "paralleldisabled",
			'sourcefile': "emake",
			'class': "EMakeParallelDisabledViaMAKEOPTS",
			'description': doc,
		},
		'autodefault-check': {
			'name': "autodefault",
			'sourcefile': "emake",
			'class': "WantAutoDefaultValue",
			'description': doc,
		},
	},
	'version': 1,
}
