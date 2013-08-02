# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['ArgumentParser']

try:
	from argparse import ArgumentParser
except ImportError:
	# Compatibility with Python 2.6 and 3.1
	from optparse import OptionGroup, OptionParser

	class ArgumentParser(object):
		def __init__(self, **kwargs):
			add_help = kwargs.pop("add_help", None)
			if add_help is not None:
				kwargs["add_help_option"] = add_help
			parser = OptionParser(**kwargs)
			self._parser = parser
			self.add_argument = parser.add_option
			self.parse_known_args = parser.parse_args
			self.parse_args = parser.parse_args

		def add_argument_group(self, title=None, **kwargs):
			optiongroup = OptionGroup(self._parser, title, **kwargs)
			self._parser.add_option_group(optiongroup)
			return _ArgumentGroup(optiongroup)

	class _ArgumentGroup(object):
		def __init__(self, optiongroup):
			self.add_argument = optiongroup.add_option
