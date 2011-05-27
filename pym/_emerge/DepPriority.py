# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractDepPriority import AbstractDepPriority
class DepPriority(AbstractDepPriority):

	__slots__ = ("satisfied", "optional", "ignored")

	def __int__(self):
		"""
		Note: These priorities are only used for measuring hardness
		in the circular dependency display via digraph.debug_print(),
		and nothing more. For actual merge order calculations, the
		measures defined by the DepPriorityNormalRange and
		DepPrioritySatisfiedRange classes are used.

		Attributes                            Hardness

		buildtime                               0
		runtime                                -1
		runtime_post                           -2
		optional                               -3
		(none of the above)                    -4

		"""

		if self.optional:
			return -3
		if self.buildtime:
			return 0
		if self.runtime:
			return -1
		if self.runtime_post:
			return -2
		return -4

	def __str__(self):
		if self.ignored:
			return "ignored"
		if self.optional:
			return "optional"
		if self.buildtime:
			return "buildtime"
		if self.runtime:
			return "runtime"
		if self.runtime_post:
			return "runtime_post"
		return "soft"

