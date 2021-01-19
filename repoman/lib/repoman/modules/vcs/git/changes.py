'''
Git module Changes class submodule
'''

import logging
import sys

from repoman._portage import portage # pylint: disable=unused-import
from repoman.modules.vcs.changes import ChangesBase
from repoman._subprocess import repoman_popen

from portage import os
from portage.package.ebuild.digestgen import digestgen
from portage.process import spawn
from portage.util import writemsg_level


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'git'

	def __init__(self, options, repo_settings):
		'''Class init

		@param options: the run time cli options
		@param repo_settings: RepoSettings instance
		'''
		super(Changes, self).__init__(options, repo_settings)

	def _scan(self, _reindex=None):
		'''
		VCS type scan function, looks for all detectable changes

		@param _reindex: ensure that the git index reflects the state on
			disk for files returned by git diff-index (this parameter is
			used in recursive calls and it's not intended to be used for
			any other reason)
		@type _reindex: bool
		'''
		# Automatically reindex for commit mode, but not for other modes
		# were the user might not want changes to be staged in the index.
		if _reindex is None and self.options.mode == 'commit':
			_reindex = True

		with repoman_popen(
			"git diff-index --name-only "
			"--relative --diff-filter=M HEAD") as f:
			changed = f.readlines()
		self.changed = ["./" + elem[:-1] for elem in changed]
		del changed

		with repoman_popen(
			"git diff-index --name-only "
			"--relative --diff-filter=A HEAD") as f:
			new = f.readlines()
		self.new = ["./" + elem[:-1] for elem in new]
		del new

		with repoman_popen(
			"git diff-index --name-only "
			"--relative --diff-filter=D HEAD") as f:
			removed = f.readlines()
		self.removed = ["./" + elem[:-1] for elem in removed]
		del removed
		if _reindex and (self.changed or self.new or self.removed):
			self.update_index([], self.changed + self.new + self.removed)
			self._scan(_reindex=False)

	@property
	def unadded(self):
		'''VCS method of getting the unadded files in the repository'''
		if self._unadded is not None:
			return self._unadded
		# get list of files not under version control or missing
		with repoman_popen("git ls-files --others") as f:
			unadded = f.readlines()
		self._unadded = ["./" + elem[:-1] for elem in unadded]
		del unadded
		return self._unadded

	def digest_regen(self, updates, removed, manifests, scanner, broken_changelog_manifests):
		'''Regenerate manifests

		@param updates: updated files
		@param removed: removed files
		@param manifests: Manifest files
		@param scanner: The repoman.scanner.Scanner instance
		@param broken_changelog_manifests: broken changelog manifests
		'''
		if broken_changelog_manifests:
			for x in broken_changelog_manifests:
				self.repoman_settings["O"] = os.path.join(self.repo_settings.repodir, x)
				digestgen(mysettings=self.repoman_settings, myportdb=self.repo_settings.portdb)

	def update_index(self, mymanifests, myupdates):
		'''Update the vcs's modified index if it is needed

		@param mymanifests: manifest files updated
		@param myupdates: other files updated'''
		# It's not safe to use the git commit -a option since there might
		# be some modified files elsewhere in the working tree that the
		# user doesn't want to commit. Therefore, call git update-index
		# in order to ensure that the index is updated with the latest
		# versions of all new and modified files in the relevant portion
		# of the working tree.
		myfiles = mymanifests + myupdates
		myfiles.sort()
		update_index_cmd = ["git", "update-index", "--add", "--remove"]
		update_index_cmd.extend(f.lstrip("./") for f in myfiles)
		if self.options.pretend:
			print("(%s)" % (" ".join(update_index_cmd),))
		else:
			retval = spawn(update_index_cmd, env=os.environ)
			if retval != os.EX_OK:
				writemsg_level(
					"!!! Exiting on %s (shell) "
					"error code: %s\n" % (self.vcs_settings.vcs, retval),
					level=logging.ERROR, noiselevel=-1)
				sys.exit(retval)

	def commit(self, myfiles, commitmessagefile):
		'''Git commit function

		@param commitfiles: list of files to commit
		@param commitmessagefile: file containing the commit message
		@returns: The sub-command exit value or 0
		'''
		retval = super(Changes, self).commit(myfiles, commitmessagefile)
		if retval != os.EX_OK:
			if self.repo_settings.repo_config.sign_commit and not self.vcs_settings.status.supports_gpg_sign():
				# Inform user that newer git is needed (bug #403323).
				logging.error(
					"Git >=1.7.9 is required for signed commits!")
		return retval
