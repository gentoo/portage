

from repoman.modules.vcs.changes import ChangesBase
from repoman._subprocess import repoman_popen


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'svn'

	def __init__(self, options):
		super(Changes, self).__init__(options)

	def _scan(self):
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
