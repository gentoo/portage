# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Uri plug-in module for repoman LineChecks.
Performs HOMEPAGE variable checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'httpsuri-check': {
			'name': "httpsuri",
			'sourcefile': "uri",
			'class': "UriUseHttps",
			'description': doc,
		},
	},
	'version': 1,
}
