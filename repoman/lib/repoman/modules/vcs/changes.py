'''
Base Changes class
'''

import logging
import os
import subprocess
import sys
from itertools import chain

from repoman._portage import portage
from portage import _unicode_encode
from portage.process import spawn


class ChangesBase:
	'''Base Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'None'

	def __init__(self, options, repo_settings):
		'''Class init function

		@param options: the run time cli options
		@param repo_settings: RepoSettings instance
		'''
		self.options = options
		self.repo_settings = repo_settings
		self.repoman_settings = repo_settings.repoman_settings
		self.vcs_settings = repo_settings.vcs_settings
		self._reset()

	def _reset(self):
		'''Reset the class variables for a new run'''
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
		'''Scan the vcs for detectable changes.

		base method which calls the subclassing VCS module's _scan()
		then updates some classwide variables.
		'''
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

	def thick_manifest(self, updates, headers, no_expansion, expansion):
		'''Create a thick manifest

		@param updates:
		@param headers:
		@param no_expansion:
		@param expansion:
		'''
		pass

	def digest_regen(self, updates, removed, manifests, scanner,
					broken_changelog_manifests):
		'''Regenerate manifests

		@param updates: updated files
		@param removed: removed files
		@param manifests: Manifest files
		@param scanner: The repoman.scanner.Scanner instance
		@param broken_changelog_manifests: broken changelog manifests
		'''
		pass

	@staticmethod
	def clear_attic(headers):
		'''Old CVS leftover

		@param headers: file headers'''
		pass

	def update_index(self, mymanifests, myupdates):
		'''Update the vcs's modified index if it is needed

		@param mymanifests: manifest files updated
		@param myupdates: other files updated'''
		pass

	def add_items(self, autoadd):
		'''Add files to the vcs's modified or new index

		@param autoadd: the files to add to the vcs modified index'''
		add_cmd = [self.vcs, "add"]
		add_cmd += autoadd
		if self.options.pretend:
			portage.writemsg_stdout(
				"(%s)\n" % " ".join(add_cmd),
				noiselevel=-1)
		else:
			add_cmd = [_unicode_encode(arg) for arg in add_cmd]
			retcode = subprocess.call(add_cmd)
			if retcode != os.EX_OK:
				logging.error(
					"Exiting on %s error code: %s\n", self.vcs_settings.vcs, retcode)
				sys.exit(retcode)


	def commit(self, commitfiles, commitmessagefile):
		'''Common generic commit function

		@param commitfiles: list of files to commit
		@param commitmessagefile: file containing the commit message
		@returns: The sub-command exit value or 0
		'''
		commit_cmd = []
		commit_cmd.append(self.vcs)
		commit_cmd.extend(self.vcs_settings.vcs_global_opts)
		commit_cmd.append("commit")
		commit_cmd.extend(self.vcs_settings.vcs_local_opts)
		commit_cmd.extend(["-F", commitmessagefile])
		commit_cmd.extend(f.lstrip("./") for f in commitfiles)

		if self.options.pretend:
			print("(%s)" % (" ".join(commit_cmd),))
			return 0
		else:
			retval = spawn(commit_cmd, env=self.repo_settings.commit_env)
		return retval
