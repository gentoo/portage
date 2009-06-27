# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.Task import Task
# for an explanation on this logic, see pym/_emerge/__init__.py
import os
import sys
if os.environ.__contains__("PORTAGE_PYTHONPATH"):
	sys.path.insert(0, os.environ["PORTAGE_PYTHONPATH"])
else:
	sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "pym"))
import portage
class Blocker(Task):

	__hash__ = Task.__hash__
	__slots__ = ("root", "atom", "cp", "eapi", "satisfied")

	def __init__(self, **kwargs):
		Task.__init__(self, **kwargs)
		self.cp = portage.dep_getkey(self.atom)

	def _get_hash_key(self):
		hash_key = getattr(self, "_hash_key", None)
		if hash_key is None:
			self._hash_key = \
				("blocks", self.root, self.atom, self.eapi)
		return self._hash_key

