

from repoman.modules.vcs.changes import ChangesBase
from repoman._subprocess import repoman_popen


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'git'

	def __init__(self, options):
		super(Changes, self).__init__(options)

	def _scan(self):
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
		if self.options.if_modified == "y":
			with repoman_popen(
				"git diff-index --name-only "
				"--relative --diff-filter=D HEAD") as f:
				removed = f.readlines()
			self.removed = ["./" + elem[:-1] for elem in removed]
			del removed

