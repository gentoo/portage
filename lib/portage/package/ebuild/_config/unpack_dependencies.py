# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os, _supported_eapis
from portage.dep import use_reduce
from portage.eapi import eapi_has_automatic_unpack_dependencies
from portage.exception import InvalidDependString
from portage.localization import _
from portage.util import grabfile, writemsg

def load_unpack_dependencies_configuration(repositories):
	repo_dict = {}
	for repo in repositories.repos_with_profiles():
		for eapi in _supported_eapis:
			if eapi_has_automatic_unpack_dependencies(eapi):
				file_name = os.path.join(repo.location, "profiles", "unpack_dependencies", eapi)
				lines = grabfile(file_name, recursive=True)
				for line in lines:
					elements = line.split()
					suffix = elements[0].lower()
					if len(elements) == 1:
						writemsg(_("--- Missing unpack dependencies for '%s' suffix in '%s'\n") % (suffix, file_name))
					depend = " ".join(elements[1:])
					try:
						use_reduce(depend, eapi=eapi)
					except InvalidDependString as e:
						writemsg(_("--- Invalid unpack dependencies for '%s' suffix in '%s': '%s'\n" % (suffix, file_name, e)))
					else:
						repo_dict.setdefault(repo.name, {}).setdefault(eapi, {})[suffix] = depend

	ret = {}
	for repo in repositories.repos_with_profiles():
		for repo_name in [x.name for x in repo.masters] + [repo.name]:
			for eapi in repo_dict.get(repo_name, {}):
				for suffix, depend in repo_dict.get(repo_name, {}).get(eapi, {}).items():
					ret.setdefault(repo.name, {}).setdefault(eapi, {})[suffix] = depend

	return ret
