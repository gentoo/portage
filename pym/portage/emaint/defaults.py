# Copyright 2005-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# parser option data
CHECK = {"short": "-c", "long": "--check",
	"help": "Check for problems (a default option for most modules)",
	'status': "Checking %s for problems",
	'action': 'store_true',
	'func': 'check'
	}

FIX = {"short": "-f", "long": "--fix",
	"help": "Attempt to fix problems (a default option for most modules)",
	'status': "Attempting to fix %s",
	'action': 'store_true',
	'func': 'fix'
	}

VERSION = {"long": "--version",
	"help": "show program's version number and exit",
	'action': 'store_true',
	}

# parser options
DEFAULT_OPTIONS = {'check': CHECK, 'fix': FIX, 'version': VERSION}
