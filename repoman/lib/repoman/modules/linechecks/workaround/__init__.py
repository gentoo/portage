# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Workaround plug-in module for repoman LineChecks.
Performs checks for upstream workarounds in ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'noasneeded-check': {
			'name': "noasneeded",
			'sourcefile': "workarounds",
			'class': "NoAsNeeded",
			'description': doc,
		},
	},
	'version': 1,
}
