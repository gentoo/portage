

from repoman.modules.vcs.changes import ChangesBase
from repoman._subprocess import repoman_popen


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'hg'

	def __init__(self, options):
		super(Changes, self).__init__(options)

	def _scan(self):
		with repoman_popen("hg status --no-status --modified .") as f:
			changed = f.readlines()
		self.changed = ["./" + elem.rstrip() for elem in changed]
		with repoman_popen("hg status --no-status --added .") as f:
			new = f.readlines()
		self.new = ["./" + elem.rstrip() for elem in new]
		if self.options.if_modified == "y":
			with repoman_popen("hg status --no-status --removed .") as f:
				removed = f.readlines()
			self.removed = ["./" + elem.rstrip() for elem in removed]
			del removed
		del changed, new
