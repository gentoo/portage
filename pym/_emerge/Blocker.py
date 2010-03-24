# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.Task import Task
try:
	import portage
except ImportError:
	from os import path as osp
	import sys
	sys.path.insert(0, osp.join(osp.dirname(osp.dirname(osp.realpath(__file__))), "pym"))
	import portage
class Blocker(Task):

	__hash__ = Task.__hash__
	__slots__ = ("root", "atom", "cp", "eapi", "priority", "satisfied")

	def __init__(self, **kwargs):
		Task.__init__(self, **kwargs)
		self.cp = self.atom.cp

	def _get_hash_key(self):
		hash_key = getattr(self, "_hash_key", None)
		if hash_key is None:
			self._hash_key = \
				("blocks", self.root, self.atom, self.eapi)
		return self._hash_key

