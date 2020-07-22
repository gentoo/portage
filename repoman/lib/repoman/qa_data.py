# -*- coding:utf-8 -*-

import logging
import os

from _emerge.Package import Package

# import our initialized portage instance
from repoman import _not_installed
from repoman._portage import portage
from repoman.config import load_config


class QAData:

	def __init__(self):
		# Create the main exported data variables
		self.max_desc_len = None
		self.allowed_filename_chars = None
		self.qahelp = None
		self.qacats = None
		self.qawarnings = None
		self.missingvars = None
		self.allvars = None
		self.valid_restrict = None
		self.suspect_rdepend = None
		self.suspect_virtual = None
		self.ruby_deprecated = None
		self.no_exec = None


	def load_repo_config(self, repopaths, options, valid_versions):
		'''Load the repository repoman qa_data.yml config

		@param repopaths: list of strings, The path of the repository being scanned
						 This could be a parent repository using the
						 repoman_masters layout.conf variable
		'''
		# add our base qahelp
		repository_modules = options.experimental_repository_modules == 'y'
		if _not_installed:
			cnfdir = os.path.realpath(os.path.join(os.path.dirname(
				os.path.dirname(os.path.dirname(__file__))), 'cnf/qa_data'))
		else:
			cnfdir = os.path.join(portage.const.EPREFIX or '/', 'usr/share/repoman/qa_data')
		repomanpaths = [os.path.join(cnfdir, _file_) for _file_ in os.listdir(cnfdir)]
		logging.debug("QAData: cnfdir: %s, repomanpaths: %s", cnfdir, repomanpaths)
		if repository_modules:
			repopaths = [os.path.join(path,'qa_data.yaml') for path in repopaths]
		elif _not_installed:
			repopaths = [os.path.realpath(os.path.join(os.path.dirname(
				os.path.dirname(os.path.dirname(__file__))),
				'cnf/repository/qa_data.yaml'))]
		else:
			repopaths = [os.path.join(portage.const.EPREFIX or '/',
				'usr/share/repoman/repository/qa_data.yaml')]
		infopaths = repomanpaths + repopaths

		qadata = load_config(infopaths, None, valid_versions)
		if qadata == {}:
			logging.error("QAData: Failed to load a valid 'qa_data.yaml' file at paths: %s", infopaths)
			return False
		self.max_desc_len = qadata.get('max_description_length', 80)
		self.allowed_filename_chars = qadata.get("allowed_filename_chars", "a-zA-Z0-9._-+:")

		self.qahelp = qadata["qahelp"]
		logging.debug("qa_help primary keys: %s", sorted(self.qahelp))

		self.qacats = []
		for x in sorted(self.qahelp):
			for y in sorted(self.qahelp[x]):
				self.qacats.append('.'.join([x, y]))
		self.qacats.sort()

		self.qawarnings = set(qadata.get('qawarnings', []))
		if options.experimental_inherit == 'y':
			# This is experimental, so it's non-fatal.
			self.qawarnings.add("inherit.missing")

		self.missingvars = qadata.get("missingvars", [])
		logging.debug("QAData: missingvars: %s", self.missingvars)
		self.allvars = set(x for x in portage.auxdbkeys if not x.startswith("UNUSED_"))
		self.allvars.update(Package.metadata_keys)
		self.allvars = sorted(self.allvars)

		for x in self.missingvars:
			x += ".missing"
			if x not in self.qacats:
				logging.warning('QAData: * missingvars values need to be added to qahelp ("%s")' % x)
				self.qacats.append(x)
				self.qawarnings.add(x)

		self.valid_restrict = frozenset(qadata.get("valid_restrict", []))

		self.suspect_rdepend = frozenset(qadata.get("suspect_rdepend", []))

		self.suspect_virtual = qadata.get("suspect_virtual", {})

		self.ruby_deprecated = frozenset(qadata.get("ruby_deprecated", []))

		# file.executable
		self.no_exec = frozenset(qadata.get("no_exec_files", []))
		logging.debug("QAData: completed loading file: %s", repopaths)
		return True


def format_qa_output(
	formatter, fails, dofull, dofail, options, qawarnings):
	"""Helper function that formats output properly

	@param formatter: an instance of Formatter
	@type formatter: Formatter
	@param fails: dict of qa status failures
	@type fails: dict
	@param dofull: Whether to print full results or a summary
	@type dofull: boolean
	@param dofail: Whether failure was hard or soft
	@type dofail: boolean
	@param options: The command-line options provided to repoman
	@type options: Namespace
	@param qawarnings: the set of warning types
	@type qawarnings: set
	@return: None (modifies formatter)
	"""
	full = options.mode == 'full'
	# we only want key value pairs where value > 0
	for category in sorted(fails):
		number = len(fails[category])
		formatter.add_literal_data("  " + category)
		spacing_width = 30 - len(category)
		if category in qawarnings:
			formatter.push_style("WARN")
		else:
			formatter.push_style("BAD")
			formatter.add_literal_data(" [fatal]")
			spacing_width -= 8

		formatter.add_literal_data(" " * spacing_width)
		formatter.add_literal_data("%s" % number)
		formatter.pop_style()
		formatter.add_line_break()
		if not dofull:
			if not full and dofail and category in qawarnings:
				# warnings are considered noise when there are failures
				continue
			fails_list = fails[category]
			if not full and len(fails_list) > 12:
				fails_list = fails_list[:12]
			for failure in fails_list:
				formatter.add_literal_data("   " + failure)
				formatter.add_line_break()


def format_qa_output_column(
	formatter, fails, dofull, dofail, options, qawarnings):
	"""Helper function that formats output in a machine-parseable column format

	@param formatter: an instance of Formatter
	@type formatter: Formatter
	@param fails: dict of qa status failures
	@type fails: dict
	@param dofull: Whether to print full results or a summary
	@type dofull: boolean
	@param dofail: Whether failure was hard or soft
	@type dofail: boolean
	@param options: The command-line options provided to repoman
	@type options: Namespace
	@param qawarnings: the set of warning types
	@type qawarnings: set
	@return: None (modifies formatter)
	"""
	full = options.mode == 'full'
	for category in sorted(fails):
		number = len(fails[category])
		formatter.add_literal_data("NumberOf " + category + " ")
		if category in qawarnings:
			formatter.push_style("WARN")
		else:
			formatter.push_style("BAD")
		formatter.add_literal_data("%s" % number)
		formatter.pop_style()
		formatter.add_line_break()
		if not dofull:
			if not full and dofail and category in qawarnings:
				# warnings are considered noise when there are failures
				continue
			fails_list = fails[category]
			if not full and len(fails_list) > 12:
				fails_list = fails_list[:12]
			for failure in fails_list:
				formatter.add_literal_data(category + " " + failure)
				formatter.add_line_break()
