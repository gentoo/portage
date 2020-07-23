# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.util.SlotObject import SlotObject
from _emerge.DepPriority import DepPriority

class Dependency(SlotObject):
	__slots__ = ("atom", "blocker", "child", "depth",
		"parent", "onlydeps", "priority", "root", "want_update",
		"collapsed_parent", "collapsed_priority")
	def __init__(self, **kwargs):
		SlotObject.__init__(self, **kwargs)
		if self.priority is None:
			self.priority = DepPriority()
		if self.depth is None:
			self.depth = 0
		if self.collapsed_parent is None:
			self.collapsed_parent = self.parent
		if self.collapsed_priority is None:
			self.collapsed_priority = self.priority
