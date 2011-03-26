# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AsynchronousTask import AsynchronousTask
from portage.output import colorize
class PackageMerge(AsynchronousTask):
	__slots__ = ("merge",)

	def _start(self):

		pkg = self.merge.pkg
		pkg_count = self.merge.pkg_count

		if pkg.installed:
			action_desc = "Uninstalling"
			preposition = "from"
			counter_str = ""
		else:
			action_desc = "Installing"
			preposition = "to"
			counter_str = "(%s of %s) " % \
				(colorize("MERGE_LIST_PROGRESS", str(pkg_count.curval)),
				colorize("MERGE_LIST_PROGRESS", str(pkg_count.maxval)))

		msg = "%s %s%s" % \
			(action_desc,
			counter_str,
			colorize("GOOD", pkg.cpv))

		if pkg.root != "/":
			msg += " %s %s" % (preposition, pkg.root)

		if not self.merge.build_opts.fetchonly and \
			not self.merge.build_opts.pretend and \
			not self.merge.build_opts.buildpkgonly:
			self.merge.statusMessage(msg)

		self.merge.merge(self.exit_handler)

	def exit_handler(self, task):
		self.returncode = task.returncode
		self._wait_hook()

