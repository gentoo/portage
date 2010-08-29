# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.Task import Task

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

