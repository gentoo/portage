
import logging
import sys


class QATracker:
	'''Track all occurrances of Q/A problems detected'''

	def __init__(self, qacats=None, qawarnings=None):
		self.fails = {}
		self.warns = {}
		self.qacats = qacats
		self.qawarnings = qawarnings

	def add_error(self, detected_qa, info):
		'''Add the Q/A error to the database of detected problems

		@param detected_qa: string, member of qa_data.qacats list
		@param info: string, details of the detected problem
		'''
		if detected_qa not in self.qacats:
			logging.error(
				'QATracker: Exiting on error. Unknown detected_qa type passed '
				'in to add_error(): %s, %s' % (detected_qa, info))
			sys.exit(1)
		try:
			self.fails[detected_qa].append(info)
		except KeyError:
			self.fails[detected_qa] = [info]

	def add_warning(self, detected_qa, info):
		'''Add the Q/A warning to the database of detected problems

		@param detected_qa: string, member of qa_data.qawarnings list
		@param info: string, details of the detected problem
		'''
		if detected_qa not in self.qawarnings:
			logging.error(
				'QATracker: Exiting on error. Unknown detected_qa type passed '
				'in to add_warning(): %s, %s' % (detected_qa, info))
			sys.exit(1)
		try:
			self.warns[detected_qa].append(info)
		except KeyError:
			self.warns[detected_qa] = [info]
