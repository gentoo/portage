# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractDepPriority import AbstractDepPriority
class UnmergeDepPriority(AbstractDepPriority):
	__slots__ = ("ignored", "optional", "satisfied",)
	"""
	Combination of properties           Priority  Category

	runtime                                0       HARD
	runtime_post                          -1       HARD
	buildtime                             -2       SOFT
	(none of the above)                   -2       SOFT
	"""

	MAX    =  0
	SOFT   = -2
	MIN    = -2

	def __init__(self, **kwargs):
		AbstractDepPriority.__init__(self, **kwargs)
		if self.buildtime:
			self.optional = True

	def __int__(self):
		if self.runtime:
			return 0
		if self.runtime_post:
			return -1
		if self.buildtime:
			return -2
		return -2

	def __str__(self):
		if self.ignored:
			return "ignored"
		myvalue = self.__int__()
		if myvalue > self.SOFT:
			return "hard"
		return "soft"

