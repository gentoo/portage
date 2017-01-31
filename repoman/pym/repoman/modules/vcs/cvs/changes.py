'''
CVS module Changes class submodule
'''

import re
from itertools import chain

from repoman._portage import portage
from repoman.modules.vcs.changes import ChangesBase
from repoman.modules.vcs.vcs import vcs_files_to_cps
from repoman._subprocess import repoman_getstatusoutput

from portage import _encodings, _unicode_encode
from portage import cvstree, os
from portage.output import green
from portage.package.ebuild.digestgen import digestgen


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'cvs'

	def __init__(self, options, repo_settings):
		'''Class init

		@param options: the run time cli options
		@param repo_settings: RepoSettings instance
		'''
		super(Changes, self).__init__(options, repo_settings)
		self._tree = None

	def _scan(self):
		'''VCS type scan function, looks for all detectable changes'''
		self._tree = portage.cvstree.getentries("./", recursive=1)
		self.changed = cvstree.findchanged(self._tree, recursive=1, basedir="./")
		self.new = cvstree.findnew(self._tree, recursive=1, basedir="./")
		self.removed = cvstree.findremoved(self._tree, recursive=1, basedir="./")
		bin_blob_pattern = re.compile("^-kb$")
		self.no_expansion = set(portage.cvstree.findoption(
			self._tree, bin_blob_pattern, recursive=1, basedir="./"))

	@property
	def unadded(self):
		'''VCS method of getting the unadded files in the repository'''
		if self._unadded is not None:
			return self._unadded
		self._unadded = portage.cvstree.findunadded(self._tree, recursive=1, basedir="./")
		return self._unadded

	@staticmethod
	def clear_attic(headers):
		'''Clear the attic (inactive files)

		@param headers: file headers
		'''
		cvs_header_re = re.compile(br'^#\s*\$Header.*\$$')
		attic_str = b'/Attic/'
		attic_replace = b'/'
		for x in headers:
			f = open(
				_unicode_encode(x, encoding=_encodings['fs'], errors='strict'),
				mode='rb')
			mylines = f.readlines()
			f.close()
			modified = False
			for i, line in enumerate(mylines):
				if cvs_header_re.match(line) is not None and \
					attic_str in line:
					mylines[i] = line.replace(attic_str, attic_replace)
					modified = True
			if modified:
				portage.util.write_atomic(x, b''.join(mylines), mode='wb')

	def thick_manifest(self, updates, headers, no_expansion, expansion):
		'''Create a thick manifest

		@param updates:
		@param headers:
		@param no_expansion:
		@param expansion:
		'''
		headerstring = r"'\$(Header|Id).*\$'"

		for _file in updates:

			# for CVS, no_expansion contains files that are excluded from expansion
			if _file in no_expansion:
				continue

			_out = repoman_getstatusoutput(
				"egrep -q %s %s" % (headerstring, portage._shell_quote(_file)))
			if _out[0] == 0:
				headers.append(_file)

		print("%s have headers that will change." % green(str(len(headers))))
		print(
			"* Files with headers will"
			" cause the manifests to be changed and committed separately.")

	def digest_regen(self, updates, removed, manifests, scanner, broken_changelog_manifests):
		'''Regenerate manifests

		@param updates: updated files
		@param removed: removed files
		@param manifests: Manifest files
		@param scanner: The repoman.scanner.Scanner instance
		@param broken_changelog_manifests: broken changelog manifests
		'''
		if updates or removed:
			for x in sorted(vcs_files_to_cps(
				chain(updates, removed, manifests),
				self.repo_settings.repodir,
				scanner.repolevel, scanner.reposplit, scanner.categories)):
				self.repoman_settings["O"] = os.path.join(self.repo_settings.repodir, x)
				digestgen(mysettings=self.repoman_settings, myportdb=self.repo_settings.portdb)
