

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
		if self.options.if_modified == "y":
			self.removed = [
				"./" + elem.split()[-1:][0]
				for elem in svnstatus
				if elem.startswith("D")]

