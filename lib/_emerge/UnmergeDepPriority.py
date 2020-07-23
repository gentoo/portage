# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractDepPriority import AbstractDepPriority
class UnmergeDepPriority(AbstractDepPriority):
	__slots__ = ("ignored", "optional", "satisfied",)
	"""
	Combination of properties           Priority  Category

	runtime_slot_op                        0       HARD
	runtime                               -1       HARD
	runtime_post                          -2       HARD
	buildtime                             -3       SOFT
	(none of the above)                   -3       SOFT
	"""

	MAX    =  0
	SOFT   = -3
	MIN    = -3

	def __init__(self, **kwargs):
		AbstractDepPriority.__init__(self, **kwargs)
		if self.buildtime:
			self.optional = True

	def __int__(self):
		if self.runtime_slot_op:
			return 0
		if self.runtime:
			return -1
		if self.runtime_post:
			return -2
		if self.buildtime:
			return -3
		return -3

	def __str__(self):
		if self.ignored:
			return "ignored"
		if self.runtime_slot_op:
			return "hard slot op"
		myvalue = self.__int__()
		if myvalue > self.SOFT:
			return "hard"
		return "soft"
