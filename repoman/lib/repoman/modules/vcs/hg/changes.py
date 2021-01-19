'''
Mercurial module Changes class submodule
'''

from repoman._portage import portage # pylint: disable=unused-import
from repoman.modules.vcs.changes import ChangesBase
from repoman._subprocess import repoman_popen

from portage import os
from portage.package.ebuild.digestgen import digestgen
from portage.process import spawn


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'hg'

	def __init__(self, options, repo_settings):
		'''Class init

		@param options: the run time cli options
		@param repo_settings: RepoSettings instance
		'''
		super(Changes, self).__init__(options, repo_settings)

	def _scan(self):
		'''VCS type scan function, looks for all detectable changes'''
		with repoman_popen("hg status --no-status --modified .") as f:
			changed = f.readlines()
		self.changed = ["./" + elem.rstrip() for elem in changed]
		del changed

		with repoman_popen("hg status --no-status --added .") as f:
			new = f.readlines()
		self.new = ["./" + elem.rstrip() for elem in new]
		del new

		with repoman_popen("hg status --no-status --removed .") as f:
			removed = f.readlines()
		self.removed = ["./" + elem.rstrip() for elem in removed]
		del removed

	@property
	def unadded(self):
		'''VCS method of getting the unadded files in the repository'''
		if self._unadded is not None:
			return self._unadded
		with repoman_popen("hg status --no-status --unknown .") as f:
			unadded = f.readlines()
		self._unadded = ["./" + elem.rstrip() for elem in unadded]
		del unadded
		return self._unadded

	@property
	def deleted(self):
		'''VCS method of getting the deleted files in the repository'''
		if self._deleted is not None:
			return self._deleted
		# Mercurial doesn't handle manually deleted files as removed from
		# the repository, so the user need to remove them before commit,
		# using "hg remove [FILES]"
		with repoman_popen("hg status --no-status --deleted .") as f:
			deleted = f.readlines()
		self._deleted = ["./" + elem.rstrip() for elem in deleted]
		del deleted
		return self._deleted


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

	def commit(self, myfiles, commitmessagefile):
		'''Hg commit function

		@param commitfiles: list of files to commit
		@param commitmessagefile: file containing the commit message
		@returns: The sub-command exit value or 0
		'''
		commit_cmd = []
		commit_cmd.append(self.vcs)
		commit_cmd.extend(self.vcs_settings.vcs_global_opts)
		commit_cmd.append("commit")
		commit_cmd.extend(self.vcs_settings.vcs_local_opts)
		commit_cmd.extend(["--logfile", commitmessagefile])
		commit_cmd.extend(myfiles)

		if self.options.pretend:
			print("(%s)" % (" ".join(commit_cmd),))
			return 0
		else:
			retval = spawn(commit_cmd, env=self.repo_settings.commit_env)
		return retval
