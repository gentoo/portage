# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Portage plug-in module for repoman LineChecks.
Performs checks for internal portage variable usage in ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'internal-check': {
			'name': "portageinternal",
			'sourcefile': "internal",
			'class': "PortageInternal",
			'description': doc,
		},
		'portageinternalvariableassignment-check': {
			'name': "portageinternalvariableassignment",
			'sourcefile': "internal",
			'class': "PortageInternalVariableAssignment",
			'description': doc,
		},
	},
	'version': 1,
}
