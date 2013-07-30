# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['ArgumentParser']

try:
	from argparse import ArgumentParser
except ImportError:
	# Compatibility with Python 2.6 and 3.1
	from optparse import OptionParser

	class ArgumentParser(object):
		def __init__(self, **kwargs):
			add_help = kwargs.pop("add_help", None)
			if add_help is not None:
				kwargs["add_help_option"] = add_help
			parser = OptionParser(**kwargs)
			self.add_argument = parser.add_option
			self.parse_known_args = parser.parse_args
			self.parse_args = parser.parse_args
