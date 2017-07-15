# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Gentoo-header plug-in module for repoman LineChecks.
Performs header checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'do',
	'description': doc,
	'provides':{
		'header-check': {
			'name': "gentooheader",
			'sourcefile': "header",
			'class': "EbuildHeader",
			'description': doc,
		},
	}
}

