# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.output import colorize, create_color_func
bad = create_color_func("BAD")

from _emerge.format_size import format_size

class PackageCounters(object):

	def __init__(self):
		self.upgrades   = 0
		self.downgrades = 0
		self.new        = 0
		self.newslot    = 0
		self.reinst     = 0
		self.uninst     = 0
		self.blocks     = 0
		self.blocks_satisfied         = 0
		self.totalsize  = 0
		self.restrict_fetch           = 0
		self.restrict_fetch_satisfied = 0
		self.interactive              = 0
		self.binary                   = 0

	def __str__(self):
		total_installs = self.upgrades + self.downgrades + self.newslot + self.new + self.reinst
		myoutput = []
		details = []
		myoutput.append("Total: %s package" % total_installs)
		if total_installs != 1:
			myoutput.append("s")
		if total_installs != 0:
			myoutput.append(" (")
		if self.upgrades > 0:
			details.append("%s upgrade" % self.upgrades)
			if self.upgrades > 1:
				details[-1] += "s"
		if self.downgrades > 0:
			details.append("%s downgrade" % self.downgrades)
			if self.downgrades > 1:
				details[-1] += "s"
		if self.new > 0:
			details.append("%s new" % self.new)
		if self.newslot > 0:
			details.append("%s in new slot" % self.newslot)
			if self.newslot > 1:
				details[-1] += "s"
		if self.reinst > 0:
			details.append("%s reinstall" % self.reinst)
			if self.reinst > 1:
				details[-1] += "s"
		if self.binary > 0:
			details.append("%s binary" % self.binary)
			if self.binary > 1:
				details[-1] = details[-1][:-1] + "ies"
		if self.uninst > 0:
			details.append("%s uninstall" % self.uninst)
			if self.uninst > 1:
				details[-1] += "s"
		if self.interactive > 0:
			details.append("%s %s" % (self.interactive,
				colorize("WARN", "interactive")))
		myoutput.append(", ".join(details))
		if total_installs != 0:
			myoutput.append(")")
		myoutput.append(", Size of downloads: %s" % format_size(self.totalsize))
		if self.restrict_fetch:
			myoutput.append("\nFetch Restriction: %s package" % \
				self.restrict_fetch)
			if self.restrict_fetch > 1:
				myoutput.append("s")
		if self.restrict_fetch_satisfied < self.restrict_fetch:
			myoutput.append(bad(" (%s unsatisfied)") % \
				(self.restrict_fetch - self.restrict_fetch_satisfied))
		if self.blocks > 0:
			myoutput.append("\nConflict: %s block" % \
				self.blocks)
			if self.blocks > 1:
				myoutput.append("s")
			if self.blocks_satisfied < self.blocks:
				myoutput.append(bad(" (%s unsatisfied)") % \
					(self.blocks - self.blocks_satisfied))
		return "".join(myoutput)

