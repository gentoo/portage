
import re

from repoman.modules.linechecks.base import LineCheck


class InheritDeprecated(LineCheck):
	"""Check if ebuild directly or indirectly inherits a deprecated eclass."""

	repoman_check_name = 'inherit.deprecated'

	# deprecated eclass : new eclass (False if no new eclass)
	deprecated_eclasses = {
		"base": False,
		"bash-completion": "bash-completion-r1",
		"boost-utils": False,
		"clutter": "gnome2",
		"confutils": False,
		"distutils": "distutils-r1",
		"games": False,
		"gems": "ruby-fakegem",
		"gpe": False,
		"gst-plugins-bad": "gstreamer",
		"gst-plugins-base": "gstreamer",
		"gst-plugins-good": "gstreamer",
		"gst-plugins-ugly": "gstreamer",
		"gst-plugins10": "gstreamer",
		"mono": "mono-env",
		"python": "python-r1 / python-single-r1 / python-any-r1",
		"ruby": "ruby-ng",
		"x-modular": "xorg-2",
	}

	_inherit_re = re.compile(r'^\s*inherit\s(.*)$')

	def new(self, pkg):
		self._errors = []

	def check(self, num, line):
		direct_inherits = None
		m = self._inherit_re.match(line)
		if m is not None:
			direct_inherits = m.group(1)
			if direct_inherits:
				direct_inherits = direct_inherits.split()

		if not direct_inherits:
			return

		for eclass in direct_inherits:
			replacement = self.deprecated_eclasses.get(eclass)
			if replacement is None:
				pass
			elif replacement is False:
				self._errors.append(
					"please migrate from "
					"'%s' (no replacement) on line: %d" % (eclass, num + 1))
			else:
				self._errors.append(
					"please migrate from "
					"'%s' to '%s' on line: %d" % (eclass, replacement, num + 1))

	def end(self):
		for error in self._errors:
			yield error
		del self._errors
