'''
CVS module Changes class submodule
'''

import re

from repoman._portage import portage
from repoman.modules.vcs.changes import ChangesBase
from portage import cvstree


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'cvs'

	def __init__(self, options):
		'''Class init

		@param options: commandline options
		'''
		super(Changes, self).__init__(options)
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
	def thick_manifest(self, myupdates, myheaders, no_expansion, expansion):
		headerstring = "'\$(Header|Id).*\$'"

		for myfile in myupdates:

			# for CVS, no_expansion contains files that are excluded from expansion
			if myfile in no_expansion:
				continue

			myout = repoman_getstatusoutput(
				"egrep -q %s %s" % (headerstring, portage._shell_quote(myfile)))
			if myout[0] == 0:
				myheaders.append(myfile)

		print("%s have headers that will change." % green(str(len(myheaders))))
		print(
			"* Files with headers will"
			" cause the manifests to be changed and committed separately.")

