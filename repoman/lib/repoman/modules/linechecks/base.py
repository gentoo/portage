
import logging
import re


class LineCheck:
	"""Run a check on a line of an ebuild."""
	"""A regular expression to determine whether to ignore the line"""
	ignore_line = False
	"""True if lines containing nothing more than comments with optional
	leading whitespace should be ignored"""
	ignore_comment = True

	def __init__(self, errors):
		self.errors = errors

	def new(self, pkg):
		pass

	def check_eapi(self, eapi):
		"""Returns if check should be run in the given EAPI (default: True)"""
		return True

	def check(self, num, line):
		"""Run the check on line and return error if there is one"""
		if self.re.match(line):
			return self.errors[self.error]

	def end(self):
		pass


class InheritEclass(LineCheck):
	"""
	Base class for checking for missing inherits, as well as excess inherits.

	Args:
		eclass: Set to the name of your eclass.
		funcs: A tuple of functions that this eclass provides.
		comprehensive: Is the list of functions complete?
		exempt_eclasses: If these eclasses are inherited, disable the missing
			inherit check.
	"""

	def __init__(
		self, eclass, eclass_eapi_functions, errors, funcs=None, comprehensive=False,
		exempt_eclasses=None, ignore_missing=False, **kwargs):
		self._eclass = eclass
		self._comprehensive = comprehensive
		self._exempt_eclasses = exempt_eclasses
		self._ignore_missing = ignore_missing
		self.errors = errors
		inherit_re = eclass
		self._eclass_eapi_functions = eclass_eapi_functions
		self._inherit_re = re.compile(
			r'^(\s*|.*[|&]\s*)\binherit\s(.*\s)?%s(\s|$)' % inherit_re)
		# Match when the function is preceded only by leading whitespace, a
		# shell operator such as (, {, |, ||, or &&, or optional variable
		# setting(s). This prevents false positives in things like elog
		# messages, as reported in bug #413285.
		logging.debug("InheritEclass, eclass: %s, funcs: %s", eclass, funcs)
		self._func_re = re.compile(
			r'(^|[|&{(])\s*(\w+=.*)?\b(' + r'|'.join(funcs) + r')\b')

	def new(self, pkg):
		self.repoman_check_name = 'inherit.missing'
		# We can't use pkg.inherited because that tells us all the eclasses that
		# have been inherited and not just the ones we inherit directly.
		self._inherit = False
		self._func_call = False
		if self._exempt_eclasses is not None:
			inherited = pkg.inherited
			self._disabled = any(x in inherited for x in self._exempt_eclasses)
		else:
			self._disabled = False
		self._eapi = pkg.eapi

	def check(self, num, line):
		if not self._inherit:
			self._inherit = self._inherit_re.match(line)
		if not self._inherit:
			if self._disabled or self._ignore_missing:
				return
			s = self._func_re.search(line)
			if s is not None:
				func_name = s.group(3)
				eapi_func = self._eclass_eapi_functions.get(func_name)
				if eapi_func is None or not eapi_func(self._eapi):
					self._func_call = True
					return (
						'%s.eclass not inherited, but "%s" called' %
						(self._eclass, func_name))
		elif not self._func_call:
			self._func_call = self._func_re.search(line)

	def end(self):
		if not self._disabled and self._comprehensive and self._inherit \
			and not self._func_call:
			self.repoman_check_name = 'inherit.unused'
			yield 'no function called from %s.eclass; please drop' % self._eclass
