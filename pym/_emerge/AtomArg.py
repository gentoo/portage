# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.DependencyArg import DependencyArg

# for an explanation on this logic, see pym/_emerge/__init__.py
import os
import sys
if os.environ.__contains__("PORTAGE_PYTHONPATH"):
	sys.path.insert(0, os.environ["PORTAGE_PYTHONPATH"])
else:
	sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "pym"))
import portage

class AtomArg(DependencyArg):
	def __init__(self, atom=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.atom = atom
		if not isinstance(self.atom, portage.dep.Atom):
			self.atom = portage.dep.Atom(self.atom)
		self.set = (self.atom, )

