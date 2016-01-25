

from repoman.modules.vcs.changes import ChangesBase


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	def __init__(self, options):
		super(Changes, self).__init__(options)

	def scan(self, vcs_settings):
		pass
