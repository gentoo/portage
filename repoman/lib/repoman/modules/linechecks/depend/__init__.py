# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Depend plug-in module for repoman LineChecks.
Performs dependency checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'depend',
	'description': doc,
	'provides':{
		'implicit-check': {
			'name': "implicitdepend",
			'sourcefile': "implicit",
			'class': "ImplicitRuntimeDeps",
			'description': doc,
		},
	},
	'version': 1,
}
