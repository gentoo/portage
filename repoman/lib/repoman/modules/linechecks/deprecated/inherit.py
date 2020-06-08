
import re

from repoman.modules.linechecks.base import LineCheck


class InheritDeprecated(LineCheck):
	"""Check if ebuild directly or indirectly inherits a deprecated eclass."""

	repoman_check_name = 'inherit.deprecated'

	# deprecated eclass : new eclass (False if no new eclass)
	deprecated_eclasses = {
		"autotools-multilib": "multilib-minimal",
		"autotools-utils": False,
		"base": False,
		"bash-completion": "bash-completion-r1",
		"boost-utils": False,
		"clutter": "gnome2",
		"cmake-utils": "cmake",
		"confutils": False,
		"distutils": "distutils-r1",
		"epatch": "(eapply since EAPI 6)",
		"fdo-mime": "xdg-utils",
		"games": False,
		"gems": "ruby-fakegem",
		"git-2": "git-r3",
		"gpe": False,
		"gst-plugins-bad": "gstreamer",
		"gst-plugins-base": "gstreamer",
		"gst-plugins-good": "gstreamer",
		"gst-plugins-ugly": "gstreamer",
		"gst-plugins10": "gstreamer",
		"ltprune": False,
		"mono": "mono-env",
		"python": "python-r1 / python-single-r1 / python-any-r1",
		"ruby": "ruby-ng",
		"user": "GLEP 81",
		"versionator": "eapi7-ver (built-in since EAPI 7)",
		"x-modular": "xorg-2",
		"xfconf": False,
	}

	_inherit_re = re.compile(r'^\s*inherit\s(.*)$')

	def check(self, num, line):
		direct_inherits = None
		m = self._inherit_re.match(line)
		if m is not None:
			direct_inherits = m.group(1)
			if direct_inherits:
				direct_inherits = direct_inherits.split()

		if not direct_inherits:
			return

		errors = []
		for eclass in direct_inherits:
			replacement = self.deprecated_eclasses.get(eclass)
			if replacement is None:
				pass
			elif replacement is False:
				errors.append(
					"please migrate from "
					"'%s' (no replacement)" % eclass)
			else:
				errors.append(
					"please migrate from "
					"'%s' to '%s'" % (eclass, replacement))
		return errors
