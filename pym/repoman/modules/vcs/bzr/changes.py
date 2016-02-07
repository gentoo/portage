'''
Bazaar module Changes class submodule
'''

from repoman.modules.vcs.changes import ChangesBase
from repoman._subprocess import repoman_popen
from repoman._portage import portage
from portage import os
from portage.package.ebuild.digestgen import digestgen

class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'bzr'

	def __init__(self, options, repo_settings):
		'''Class init

		@param options: commandline options
		'''
		super(Changes, self).__init__(options, repo_settings)

	def _scan(self):
		'''VCS type scan function, looks for all detectable changes'''
		with repoman_popen("bzr status -S .") as f:
			bzrstatus = f.readlines()
		self.changed = [
			"./" + elem.split()[-1:][0].split('/')[-1:][0]
			for elem in bzrstatus
			if elem and elem[1:2] == "M"]
		self.new = [
			"./" + elem.split()[-1:][0].split('/')[-1:][0]
			for elem in bzrstatus
			if elem and (elem[1:2] == "NK" or elem[0:1] == "R")]
		self.removed = [
			"./" + elem.split()[-3:-2][0].split('/')[-1:][0]
			for elem in bzrstatus
			if elem and (elem[1:2] == "K" or elem[0:1] == "R")]
		self.bzrstatus = bzrstatus
		# Bazaar expands nothing.

	@property
	def unadded(self):
		'''Bazzar method of getting the unadded files in the repository'''
		if self._unadded is not None:
			return self._unadded
		self._unadded = [
			"./" + elem.rstrip().split()[1].split('/')[-1:][0]
			for elem in self.bzrstatus
			if elem.startswith("?") or elem[0:2] == " D"]
		return self._unadded

	def digest_regen(self, myupdates, myremoved, mymanifests, scanner, broken_changelog_manifests):
		if broken_changelog_manifests:
			for x in broken_changelog_manifests:
				self.repoman_settings["O"] = os.path.join(self.repo_settings.repodir, x)
				digestgen(mysettings=self.repoman_settings, myportdb=self.repo_settings.portdb)

