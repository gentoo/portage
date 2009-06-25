# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.DependencyArg import DependencyArg
try:
	import portage
except ImportError:
	from os import path as osp
	import sys
	sys.path.insert(0, osp.join(osp.dirname(osp.dirname(osp.realpath(__file__))), "pym"))
	import portage
class PackageArg(DependencyArg):
	def __init__(self, package=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.package = package
		self.atom = portage.dep.Atom("=" + package.cpv)
		self.set = (self.atom, )

