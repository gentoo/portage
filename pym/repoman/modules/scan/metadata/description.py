
'''description.py
Perform checks on the DESCRIPTION variable.
'''

from repoman.qa_data import max_desc_len


class DescriptionChecks(object):
	'''Perform checks on the DESCRIPTION variable.'''

	def __init__(self, **kwargs):
		'''
		@param qatracker: QATracker instance
		'''
		self.qatracker = kwargs.get('qatracker')

	def checkTooLong(self, **kwargs):
		'''
		@param pkg: Package in which we check (object).
		@param ebuild: Ebuild which we check (object).
		'''
		ebuild = kwargs.get('ebuild')
		pkg = kwargs.get('pkg')
		# 14 is the length of DESCRIPTION=""
		if len(pkg._metadata['DESCRIPTION']) > max_desc_len:
			self.qatracker.add_error(
				'DESCRIPTION.toolong',
				"%s: DESCRIPTION is %d characters (max %d)" %
				(ebuild.relative_path, len(
					pkg._metadata['DESCRIPTION']), max_desc_len))
		return {'continue': False}

	@property
	def runInPkgs(self):
		return (False, [])

	@property
	def runInEbuilds(self):
		return (True, [self.checkTooLong])
