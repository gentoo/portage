# -*- coding:utf-8 -*-

from repoman.modules.scan.scanbase import ScanBase


class ArchChecks(ScanBase):

	def __init__(self, **kwargs):
		self.options = kwargs.get('options')
		self.repo_settings = kwargs.get('repo_settings')
		self.profiles = kwargs.get('profiles')

	def check(self, **kwargs):
		ebuild = kwargs.get('ebuild')
		if self.options.ignore_arches:
			arches = [[
				self.repo_settings.repoman_settings["ARCH"], self.repo_settings.repoman_settings["ARCH"],
				self.repo_settings.repoman_settings["ACCEPT_KEYWORDS"].split()]]
		else:
			arches = set()
			for keyword in ebuild.keywords:
				if keyword[0] == "-":
					continue
				elif keyword[0] == "~":
					arch = keyword[1:]
					if arch == "*":
						for expanded_arch in self.profiles:
							if expanded_arch == "**":
								continue
							arches.add(
								(keyword, expanded_arch, (
									expanded_arch, "~" + expanded_arch)))
					else:
						arches.add((keyword, arch, (arch, keyword)))
				else:
					# For ebuilds with stable keywords, check if the
					# dependencies are satisfiable for unstable
					# configurations, since use.stable.mask is not
					# applied for unstable configurations (see bug
					# 563546).
					if keyword == "*":
						for expanded_arch in self.profiles:
							if expanded_arch == "**":
								continue
							arches.add(
								(keyword, expanded_arch, (expanded_arch,)))
							arches.add(
								(keyword, expanded_arch,
									(expanded_arch, "~" + expanded_arch)))
					else:
						arches.add((keyword, keyword, (keyword,)))
						arches.add((keyword, keyword,
							(keyword, "~" + keyword)))
			if not arches:
				# Use an empty profile for checking dependencies of
				# packages that have empty KEYWORDS.
				arches.add(('**', '**', ('**',)))
		return {'continue': False, 'arches': arches}

	@property
	def runInEbuilds(self):
		return (True, [self.check])
