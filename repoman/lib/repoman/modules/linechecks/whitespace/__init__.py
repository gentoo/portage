# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Whitespace plug-in module for repoman LineChecks.
Performs checks for useless whitespace in ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'whitespace-check': {
			'name': "whitespace",
			'sourcefile': "whitespace",
			'class': "EbuildWhitespace",
			'description': doc,
		},
		'blankline-check': {
			'name': "blankline",
			'sourcefile': "blank",
			'class': "EbuildBlankLine",
			'description': doc,
		},
	},
	'version': 1,
}
