# Copyright 2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['ConfigParserError', 'NoOptionError', 'ParsingError',
	'RawConfigParser', 'SafeConfigParser']

# the following scary compatibility thing provides two classes:
# - SafeConfigParser that provides safe interpolation for values,
# - RawConfigParser that provides no interpolation for values.

import sys

try:
	from configparser import (Error as ConfigParserError,
		NoOptionError, ParsingError, RawConfigParser)
	if sys.hexversion >= 0x3020000:
		from configparser import ConfigParser as SafeConfigParser
	else:
		from configparser import SafeConfigParser
except ImportError:
	from ConfigParser import (Error as ConfigParserError,
		NoOptionError, ParsingError, RawConfigParser, SafeConfigParser)
