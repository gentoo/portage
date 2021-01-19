# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Assignment plug-in module for repoman LineChecks.
Performs assignments checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'assignment',
	'description': doc,
	'provides':{
		'assignment-check': {
			'name': "assignment",
			'sourcefile': "assignment",
			'class': "EbuildAssignment",
			'description': doc,
		},
		'eapi3-check': {
			'name': "eapi3assignment",
			'sourcefile': "assignment",
			'class': "Eapi3EbuildAssignment",
			'description': doc,
		},
	},
	'version': 1,
}
