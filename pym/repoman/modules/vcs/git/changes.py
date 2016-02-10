'''
Git module Changes class submodule
'''

import logging
import sys

from repoman.modules.vcs.changes import ChangesBase
from repoman._subprocess import repoman_popen
from repoman._portage import portage
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

		@param options: commandline options
		'''
		super(Changes, self).__init__(options, repo_settings)

	def _scan(self):
		'''VCS type scan function, looks for all detectable changes'''
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

	def digest_regen(self, myupdates, myremoved, mymanifests, scanner, broken_changelog_manifests):
		if broken_changelog_manifests:
			for x in broken_changelog_manifests:
				self.repoman_settings["O"] = os.path.join(self.repo_settings.repodir, x)
				digestgen(mysettings=self.repoman_settings, myportdb=self.repo_settings.portdb)

	def update_index(self, mymanifests, myupdates):
		# It's not safe to use the git commit -a option since there might
		# be some modified files elsewhere in the working tree that the
		# user doesn't want to commit. Therefore, call git update-index
		# in order to ensure that the index is updated with the latest
		# versions of all new and modified files in the relevant portion
		# of the working tree.
		myfiles = mymanifests + myupdates
		myfiles.sort()
		update_index_cmd = ["git", "update-index"]
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
