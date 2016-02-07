'''
Subversion module Changes class submodule
'''

from repoman.modules.vcs.changes import ChangesBase
from repoman._subprocess import repoman_popen


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'svn'

	def __init__(self, options, repo_settings):
		'''Class init

		@param options: commandline options
		'''
		super(Changes, self).__init__(options, repo_settings)

	def _scan(self):
		'''VCS type scan function, looks for all detectable changes'''
		with repoman_popen("svn status") as f:
			svnstatus = f.readlines()
		self.changed = [
			"./" + elem.split()[-1:][0]
			for elem in svnstatus
			if elem and elem[:1] in "MR"]
		self.new = [
			"./" + elem.split()[-1:][0]
			for elem in svnstatus
			if elem.startswith("A")]
		self.removed = [
			"./" + elem.split()[-1:][0]
			for elem in svnstatus
			if elem.startswith("D")]

	@property
	def expansion(self):
		'''VCS method of getting the expanded keywords in the repository'''
		if self._expansion is not None:
			return self._expansion
		# Subversion expands keywords specified in svn:keywords properties.
		with repoman_popen("svn propget -R svn:keywords") as f:
			props = f.readlines()
		self._expansion = dict(
			("./" + prop.split(" - ")[0], prop.split(" - ")[1].split())
			for prop in props if " - " in prop)
		del props
		return self._expansion

	@property
	def unadded(self):
		'''VCS method of getting the unadded files in the repository'''
		if self._unadded is not None:
			return self._unadded
		with repoman_popen("svn status --no-ignore") as f:
			svnstatus = f.readlines()
		self._unadded = [
			"./" + elem.rstrip().split()[1]
			for elem in svnstatus
			if elem.startswith("?") or elem.startswith("I")]
		del svnstatus
		return self._unadded

	def thick_manifest(self, myupdates, myheaders, no_expansion, expansion):
		svn_keywords = dict((k.lower(), k) for k in [
			"Rev",
			"Revision",
			"LastChangedRevision",
			"Date",
			"LastChangedDate",
			"Author",
			"LastChangedBy",
			"URL",
			"HeadURL",
			"Id",
			"Header",
		])

		for myfile in myupdates:
			# for SVN, expansion contains files that are included in expansion
			if myfile not in expansion:
				continue

			# Subversion keywords are case-insensitive
			# in svn:keywords properties,
			# but case-sensitive in contents of files.
			enabled_keywords = []
			for k in expansion[myfile]:
				keyword = svn_keywords.get(k.lower())
				if keyword is not None:
					enabled_keywords.append(keyword)

			headerstring = "'\$(%s).*\$'" % "|".join(enabled_keywords)

			myout = repoman_getstatusoutput(
				"egrep -q %s %s" % (headerstring, portage._shell_quote(myfile)))
			if myout[0] == 0:
				myheaders.append(myfile)

		print("%s have headers that will change." % green(str(len(myheaders))))
		print(
			"* Files with headers will"
			" cause the manifests to be changed and committed separately.")

