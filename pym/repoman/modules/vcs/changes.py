'''
Base Changes class
'''

import os
from itertools import chain


class ChangesBase(object):
	'''Base Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'None'

	def __init__(self, options, repo_settings):
		self.options = options
		self.repo_settings = repo_settings
		self.repoman_settings = repo_settings.repoman_settings
		self._reset()

	def _reset(self):
		self.new_ebuilds = set()
		self.ebuilds = set()
		self.changelogs = set()
		self.changed = []
		self.new = []
		self.removed = []
		self.no_expansion = set()
		self._expansion = None
		self._deleted = None
		self._unadded = None

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

	@property
	def has_deleted(self):
		'''Placeholder for VCS that requires manual deletion of files'''
		return self.deleted != []

	@property
	def has_changes(self):
		'''Placeholder for VCS repo common has changes result'''
		changed = self.changed or self.new or self.removed or self.deleted
		return changed != []

	@property
	def unadded(self):
		'''Override this function as needed'''
		return []

	@property
	def deleted(self):
		'''Override this function as needed'''
		return []

	@property
	def expansion(self):
		'''Override this function as needed'''
		return {}

	def thick_manifest(self, myupdates, myheaders, no_expansion, expansion):
		'''Create a thick manifest'''
		pass

	@staticmethod
	def clear_attic(myheaders):
		'''Old CVS leftover'''
		pass
