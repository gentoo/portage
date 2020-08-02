# Copyright 2016-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ['ConfigParserError', 'NoOptionError', 'ParsingError',
	'RawConfigParser', 'SafeConfigParser', 'read_configs']

# the following scary compatibility thing provides two classes:
# - SafeConfigParser that provides safe interpolation for values,
# - RawConfigParser that provides no interpolation for values.

import io

from configparser import (Error as ConfigParserError,
	NoOptionError, ParsingError, RawConfigParser)
from configparser import ConfigParser as SafeConfigParser

from portage import _encodings
from portage import _unicode_encode


def read_configs(parser, paths):
	"""
	Read configuration files from given paths into the specified
	ConfigParser, handling path encoding portably.
	@param parser: target *ConfigParser instance
	@type parser: SafeConfigParser or RawConfigParser
	@param paths: list of paths to read
	@type paths: iterable
	"""
	# use read_file/readfp in order to control decoding of unicode
	try:
		# Python >=3.2
		read_file = parser.read_file
		source_kwarg = 'source'
	except AttributeError:
		read_file = parser.readfp
		source_kwarg = 'filename'

	for p in paths:
		if isinstance(p, str):
			f = None
			try:
				f = io.open(_unicode_encode(p,
					encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['repo.content'],
					errors='replace')
			except EnvironmentError:
				pass
			else:
				# The 'source' keyword argument is needed since otherwise
				# ConfigParser in Python <3.3.3 may throw a TypeError
				# because it assumes that f.name is a native string rather
				# than binary when constructing error messages.
				kwargs = {source_kwarg: p}
				read_file(f, **kwargs)
			finally:
				if f is not None:
					f.close()
		elif isinstance(p, io.StringIO):
			kwargs = {source_kwarg: "<io.StringIO>"}
			read_file(p, **kwargs)
		else:
			raise TypeError("Unsupported type %r of element %r of 'paths' argument" % (type(p), p))
