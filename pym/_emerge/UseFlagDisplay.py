# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys

from portage import _encodings, _unicode_encode
from portage.output import red
from portage.util import cmp_sort_key
from portage.output import blue

class UseFlagDisplay(object):

	__slots__ = ('name', 'enabled', 'forced')

	def __init__(self, name, enabled, forced):
		self.name = name
		self.enabled = enabled
		self.forced = forced

	def __str__(self):
		s = self.name
		if self.enabled:
			s = red(s)
		else:
			s = '-' + s
			s = blue(s)
		if self.forced:
			s = '(%s)' % s
		return s

	if sys.hexversion < 0x3000000:

		__unicode__ = __str__

		def __str__(self):
			return _unicode_encode(self.__unicode__(),
				encoding=_encodings['content'])

	def _cmp_combined(a, b):
		"""
		Sort by name, combining enabled and disabled flags.
		"""
		return (a.name > b.name) - (a.name < b.name)

	sort_combined = cmp_sort_key(_cmp_combined)
	del _cmp_combined

	def _cmp_separated(a, b):
		"""
		Sort by name, separating enabled flags from disabled flags.
		"""
		enabled_diff = b.enabled - a.enabled
		if enabled_diff:
			return enabled_diff
		return (a.name > b.name) - (a.name < b.name)

	sort_separated = cmp_sort_key(_cmp_separated)
	del _cmp_separated

