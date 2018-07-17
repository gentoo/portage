# -*- coding:utf-8 -*-


def _gen_arches(ebuild, options, repo_settings, profiles):
	'''Determines the arches for the ebuild following the profile rules

	@param ebuild: Ebuild which we check (object).
	@param profiles: dictionary
	@param options: cli options
	@param repo_settings: repository settings instance
	@returns: dictionary, including arches set
	'''
	if options.ignore_arches:
		arches = [[
			repo_settings.repoman_settings["ARCH"], repo_settings.repoman_settings["ARCH"],
			repo_settings.repoman_settings["ACCEPT_KEYWORDS"].split()]]
	else:
		arches = set()
		for keyword in ebuild.keywords:
			if keyword[0] == "-":
				continue
			elif keyword[0] == "~":
				arch = keyword[1:]
				if arch == "*":
					for expanded_arch in profiles:
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
					for expanded_arch in profiles:
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

	return arches
