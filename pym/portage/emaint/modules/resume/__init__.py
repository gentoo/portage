# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""'This emaint module provides checks and maintenance for:
Cleaning the "emerge --resume" lists
"""


module_spec = {
	'name': 'resume',
	'description': "Provides functions to scan, check and fix problems " +\
		"in the resume and/or resume_backup files",
	'provides':{
		'module1': {
			'name': "cleanresume",
			'class': "CleanResume",
			'description':  "Discard emerge --resume merge lists",
			'functions': ['check', 'fix'],
			'func_desc': {}
			}
		}
	}
