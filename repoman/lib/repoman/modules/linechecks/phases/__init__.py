# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Phases plug-in module for repoman LineChecks.
Performs phase dependant checks on ebuilds using a PhaseCheck base class.
"""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'emakeparallel-check': {
			'name': "emakeparallel",
			'sourcefile': "phase",
			'class': "EMakeParallelDisabled",
			'description': doc,
		},
		'srccompileeconf-check': {
			'name': "srccompileeconf",
			'sourcefile': "phase",
			'class': "SrcCompileEconf",
			'description': doc,
		},
		'srcunpackpatches-check': {
			'name': "srcunpackpatches",
			'sourcefile': "phase",
			'class': "SrcUnpackPatches",
			'description': doc,
		},
	},
	'version': 1,
}
