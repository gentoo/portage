# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.CompositeTask import CompositeTask
from portage.output import colorize
class PackageMerge(CompositeTask):
	__slots__ = ("merge",)

	def _start(self):

		self.scheduler = self.merge.scheduler
		pkg = self.merge.pkg
		pkg_count = self.merge.pkg_count
		pkg_color = "PKG_MERGE"
		if pkg.type_name == "binary":
			pkg_color = "PKG_BINARY_MERGE"

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
			colorize(pkg_color, pkg.cpv))

		if pkg.root_config.settings["ROOT"] != "/":
			msg += " %s %s" % (preposition, pkg.root)

		if not self.merge.build_opts.fetchonly and \
			not self.merge.build_opts.pretend and \
			not self.merge.build_opts.buildpkgonly:
			self.merge.statusMessage(msg)

		task = self.merge.create_install_task()
		self._start_task(task, self._default_final_exit)
