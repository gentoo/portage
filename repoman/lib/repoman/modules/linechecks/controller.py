
import logging
import operator
import os
import re

from repoman.modules.linechecks.base import InheritEclass
from repoman.modules.linechecks.config import LineChecksConfig
from repoman._portage import portage

# Avoid a circular import issue in py2.7
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.module:Modules',
)

MODULES_PATH = os.path.dirname(__file__)
# initial development debug info
logging.debug("LineChecks module path: %s", MODULES_PATH)


class LineCheckController:
	'''Initializes and runs the LineCheck checks'''

	def __init__(self, repo_settings, linechecks):
		'''Class init

		@param repo_settings: RepoSettings instance
		'''
		self.repo_settings = repo_settings
		self.linechecks = linechecks
		self.config = LineChecksConfig(repo_settings)

		self.controller = Modules(path=MODULES_PATH, namepath="repoman.modules.linechecks")
		logging.debug("LineCheckController; module_names: %s", self.controller.module_names)

		self._constant_checks = None

		self._here_doc_re = re.compile(r'.*<<[-]?(\w+)\s*(>\s*\S+\s*)?$')
		self._ignore_comment_re = re.compile(r'^\s*#')
		self._continuation_re = re.compile(r'(\\)*$')

	def checks_init(self, experimental_inherit=False):
		'''Initialize the main variables

		@param experimental_inherit boolean
		'''
		if not experimental_inherit:
			# Emulate the old eprefixify.defined and inherit.autotools checks.
			self._eclass_info = self.config.eclass_info
		else:
			self._eclass_info = self.config.eclass_info_experimental_inherit

		self._constant_checks = []
		logging.debug("LineCheckController; modules: %s", self.linechecks)
		# Add in the pluggable modules
		for mod in self.linechecks:
			mod_class = self.controller.get_class(mod)
			logging.debug("LineCheckController; module_name: %s, class: %s", mod, mod_class.__name__)
			self._constant_checks.append(mod_class(self.config.errors))
		# Add in the InheritEclass checks
		logging.debug("LineCheckController; eclass_info.items(): %s", list(self.config.eclass_info))
		for k, kwargs in self.config.eclass_info.items():
			logging.debug("LineCheckController; k: %s, kwargs: %s", k, kwargs)
			self._constant_checks.append(
				InheritEclass(
					k,
					self.config.eclass_eapi_functions,
					self.config.errors,
					**kwargs
				)
			)


	def run_checks(self, contents, pkg):
		'''Run the configured linechecks

		@param contents: the ebuild contents to check
		@param pkg: the package being checked
		'''
		if self._constant_checks is None:
			self.checks_init()
		checks = self._constant_checks
		here_doc_delim = None
		multiline = None

		for lc in checks:
			lc.new(pkg)

		multinum = 0
		for num, line in enumerate(contents):

			# Check if we're inside a here-document.
			if here_doc_delim is not None:
				if here_doc_delim.match(line):
					here_doc_delim = None
			if here_doc_delim is None:
				here_doc = self._here_doc_re.match(line)
				if here_doc is not None:
					here_doc_delim = re.compile(r'^\s*%s$' % here_doc.group(1))
			if here_doc_delim is not None:
				continue

			# Unroll multiline escaped strings so that we can check things:
			# 	inherit foo bar \
			# 		moo \
			# 		cow
			# This will merge these lines like so:
			# 	inherit foo bar moo cow
			# A line ending with an even number of backslashes does not count,
			# because the last backslash is escaped. Therefore, search for an
			# odd number of backslashes.
			line_escaped = operator.sub(*self._continuation_re.search(line).span()) % 2 == 1
			if multiline:
				# Chop off the \ and \n bytes from the previous line.
				multiline = multiline[:-2] + line
				if not line_escaped:
					line = multiline
					num = multinum
					multiline = None
				else:
					continue
			else:
				if line_escaped:
					multinum = num
					multiline = line
					continue

			if not line.endswith("#nowarn\n"):
				# Finally we have a full line to parse.
				is_comment = self._ignore_comment_re.match(line) is not None
				for lc in checks:
					if is_comment and lc.ignore_comment:
						continue
					if lc.check_eapi(pkg.eapi):
						ignore = lc.ignore_line
						if not ignore or not ignore.match(line):
							errors = lc.check(num, line)
							if errors:
								if isinstance(errors, (tuple, list)):
									for error in errors:
										yield lc.repoman_check_name, "line %d: %s" % (num + 1, error)
								else:
									yield lc.repoman_check_name, "line %d: %s" % (num + 1, errors)

		for lc in checks:
			i = lc.end()
			if i is not None:
				for e in i:
					yield lc.repoman_check_name, e
