# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SubProcess import SubProcess

class PopenProcess(SubProcess):

	__slots__ = ("proc",)

	def __init__(self, **kwargs):
		SubProcess.__init__(self, **kwargs)
		self.pid = self.proc.pid

	def _start(self):
		pass
