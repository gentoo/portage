# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.DependencyArg import DependencyArg
try:
	import portage
except ImportError:
	from os import path as osp
	import sys
	sys.path.insert(0, osp.join(osp.dirname(osp.dirname(osp.realpath(__file__))), "pym"))
	import portage
class AtomArg(DependencyArg):
	def __init__(self, atom=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.atom = atom
		self.set = (self.atom, )
