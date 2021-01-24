# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Deprecated plug-in module for repoman LineChecks.
Performs miscelaneous deprecation checks on ebuilds not covered by
specialty modules."""
__doc__ = doc[:]


module_spec = {
	'name': 'deprecated',
	'description': doc,
	'provides':{
		'useq-check': {
			'name': "useq",
			'sourcefile': "deprecated",
			'class': "DeprecatedUseq",
			'description': doc,
		},
		'hasq-check': {
			'name': "hasq",
			'sourcefile': "deprecated",
			'class': "DeprecatedHasq",
			'description': doc,
		},
		'preserve-check': {
			'name': "preservelib",
			'sourcefile': "deprecated",
			'class': "PreserveOldLib",
			'description': doc,
		},
		'bindnow-check': {
			'name': "bindnow",
			'sourcefile': "deprecated",
			'class': "DeprecatedBindnowFlags",
			'description': doc,
		},
		'inherit-check': {
			'name': "inherit",
			'sourcefile': "inherit",
			'class': "InheritDeprecated",
			'description': doc,
		},
	},
	'version': 1,
}
