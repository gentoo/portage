# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys

from portage import _encodings, _unicode_encode, _unicode_decode

class DependencyArg(object):

	__slots__ = ('arg', 'force_reinstall', 'internal', 'reset_depth', 'root_config')

	def __init__(self, arg=None, force_reinstall=False, internal=False,
		reset_depth=True, root_config=None):
		"""
		Use reset_depth=False for special arguments that should not interact
		with depth calculations (see the emerge --deep=DEPTH option).
		"""
		self.arg = arg
		self.force_reinstall = force_reinstall
		self.internal = internal
		self.reset_depth = reset_depth
		self.root_config = root_config

	def __eq__(self, other):
		if self.__class__ is not other.__class__:
			return False
		return self.arg == other.arg and \
			self.root_config.root == other.root_config.root

	def __hash__(self):
		return hash((self.arg, self.root_config.root))

	def __str__(self):
		# Force unicode format string for python-2.x safety,
		# ensuring that self.arg.__unicode__() is used
		# when necessary.
		return _unicode_decode("%s") % (self.arg,)

	if sys.hexversion < 0x3000000:

		__unicode__ = __str__

		def __str__(self):
			return _unicode_encode(self.__unicode__(), encoding=_encodings['content'])
