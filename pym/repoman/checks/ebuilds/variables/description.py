
'''description.py
Perform checks on the DESCRIPTION variable.
'''

from repoman.qa_data import max_desc_len


class DescriptionChecks(object):
	'''Perform checks on the DESCRIPTION variable.'''

	def __init__(self, qatracker):
		'''
		@param qatracker: QATracker instance
		'''
		self.qatracker = qatracker

	def check(self, pkg, ebuild):
		'''
		@param pkg: Package in which we check (object).
		@param ebuild: Ebuild which we check (object).
		'''
		self._checkTooLong(pkg, ebuild)

	def _checkTooLong(self, pkg, ebuild):
		# 14 is the length of DESCRIPTION=""
		if len(pkg._metadata['DESCRIPTION']) > max_desc_len:
			self.qatracker.add_error(
				'DESCRIPTION.toolong',
				"%s: DESCRIPTION is %d characters (max %d)" %
				(ebuild.relative_path, len(
					pkg._metadata['DESCRIPTION']), max_desc_len))
