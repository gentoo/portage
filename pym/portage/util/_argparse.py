# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['ArgumentParser']

try:
	from argparse import ArgumentParser
except ImportError:
	# Compatibility with Python 2.6 and 3.1
	from optparse import OptionGroup, OptionParser

	from portage.localization import _

	class ArgumentParser(object):
		def __init__(self, **kwargs):
			add_help = kwargs.pop("add_help", None)
			if add_help is not None:
				kwargs["add_help_option"] = add_help
			parser = OptionParser(**kwargs)
			self._parser = parser
			self.add_argument = parser.add_option
			self.print_help = parser.print_help
			self.error = parser.error

		def add_argument_group(self, title=None, **kwargs):
			optiongroup = OptionGroup(self._parser, title, **kwargs)
			self._parser.add_option_group(optiongroup)
			return _ArgumentGroup(optiongroup)

		def parse_known_args(self, args=None, namespace=None):
			return self._parser.parse_args(args, namespace)

		def parse_args(self, args=None, namespace=None):
			args, argv = self.parse_known_args(args, namespace)
			if argv:
				msg = _('unrecognized arguments: %s')
				self.error(msg % ' '.join(argv))
			return args

	class _ArgumentGroup(object):
		def __init__(self, optiongroup):
			self.add_argument = optiongroup.add_option
