# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Eapi plug-in module for repoman LineChecks.
Performs eapi dependant checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'eapi',
	'description': doc,
	'provides':{
		'definition-check': {
			'name': "definition",
			'sourcefile': "definition",
			'class': "EapiDefinition",
			'description': doc,
		},
		'srcprepare-check': {
			'name': "srcprepare",
			'sourcefile': "checks",
			'class': "UndefinedSrcPrepareSrcConfigurePhases",
			'description': doc,
		},
		'eapi3deprecated-check': {
			'name': "eapi3deprecated",
			'sourcefile': "checks",
			'class': "Eapi3DeprecatedFuncs",
			'description': doc,
		},
		'pkgpretend-check': {
			'name': "pkgpretend",
			'sourcefile': "checks",
			'class': "UndefinedPkgPretendPhase",
			'description': doc,
		},
		'eapi4incompatible-check': {
			'name': "eapi4incompatible",
			'sourcefile': "checks",
			'class': "Eapi4IncompatibleFuncs",
			'description': doc,
		},
		'eapi4gonevars-check': {
			'name': "eapi4gonevars",
			'sourcefile': "checks",
			'class': "Eapi4GoneVars",
			'description': doc,
		},
	},
	'version': 1,
}
