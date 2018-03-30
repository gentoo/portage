# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Nested plug-in module for repoman LineChecks.
Performs nested subshell checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'quote-check': {
			'name': "quote",
			'sourcefile': "quotes",
			'class': "EbuildQuote",
			'description': doc,
		},
		'quoteda-check': {
			'name': "quoteda",
			'sourcefile': "quoteda",
			'class': "EbuildQuotedA",
			'description': doc,
		},
	},
	'version': 1,
}

