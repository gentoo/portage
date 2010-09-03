# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.DependencyArg import DependencyArg
from portage._sets import SETPREFIX
class SetArg(DependencyArg):
	def __init__(self, set=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.set = set
		self.name = self.arg[len(SETPREFIX):]

