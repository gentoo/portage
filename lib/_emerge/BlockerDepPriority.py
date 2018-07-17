# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.DepPriority import DepPriority
class BlockerDepPriority(DepPriority):
	__slots__ = ()
	def __int__(self):
		return 0

	def __str__(self):
		return 'blocker'

BlockerDepPriority.instance = BlockerDepPriority()
