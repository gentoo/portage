
import os
from itertools import chain


class ChangesBase(object):
	'''Base Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'None'

	def __init__(self, options):
		self.options = options
		self._reset()

	def _reset(self):
		self.new_ebuilds = set()
		self.ebuilds = set()
		self.changelogs = set()
		self.changed = []
		self.new = []
		self.removed = []

	def scan(self):
		self._reset()

		if self.vcs:
			self._scan()
			self.new_ebuilds.update(x for x in self.new if x.endswith(".ebuild"))
			self.ebuilds.update(x for x in self.changed if x.endswith(".ebuild"))
			self.changelogs.update(
				x for x in chain(self.changed, self.new)
				if os.path.basename(x) == "ChangeLog")

	def _scan(self):
		'''Placeholder for subclassing'''
		pass

