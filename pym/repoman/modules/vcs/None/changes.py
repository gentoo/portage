'''
None module Changes class submodule
'''

from repoman.modules.vcs.changes import ChangesBase


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'None'

	def __init__(self, options):
		'''Class init

		@param options: commandline options
		'''
		super(Changes, self).__init__(options)

	def scan(self):
		'''VCS type scan function, looks for all detectable changes'''
		pass
