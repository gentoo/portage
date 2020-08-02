# -*- coding:utf-8 -*-

from __future__ import print_function

from portage import normalize_path
from portage import os
from portage.output import red


class ProfileDesc:
	__slots__ = ('abs_path', 'arch', 'status', 'sub_path', 'tree_path',)

	def __init__(self, arch, status, sub_path, tree_path):
		self.arch = arch
		self.status = status
		if sub_path:
			sub_path = normalize_path(sub_path.lstrip(os.sep))
		self.sub_path = sub_path
		self.tree_path = tree_path
		if tree_path:
			self.abs_path = os.path.join(tree_path, 'profiles', self.sub_path)
		else:
			self.abs_path = tree_path

	def __str__(self):
		if self.sub_path:
			return self.sub_path
		return 'empty profile'


valid_profile_types = frozenset(['dev', 'exp', 'stable'])


def dev_profile_keywords(profiles):
	"""
	Create a set of KEYWORDS values that exist in 'dev'
	profiles. These are used
	to trigger a message notifying the user when they might
	want to add the --include-dev option.
	"""
	type_arch_map = {}
	for arch, arch_profiles in profiles.items():
		for prof in arch_profiles:
			arch_set = type_arch_map.get(prof.status)
			if arch_set is None:
				arch_set = set()
				type_arch_map[prof.status] = arch_set
			arch_set.add(arch)

	dev_keywords = type_arch_map.get('dev', set())
	dev_keywords.update(['~' + arch for arch in dev_keywords])
	return frozenset(dev_keywords)


def setup_profile(profile_list):
	# Ensure that profile sub_path attributes are unique. Process in reverse order
	# so that profiles with duplicate sub_path from overlays will override
	# profiles with the same sub_path from parent repos.
	profiles = {}
	profile_list.reverse()
	profile_sub_paths = set()
	for prof in profile_list:
		if prof.sub_path in profile_sub_paths:
			continue
		profile_sub_paths.add(prof.sub_path)
		profiles.setdefault(prof.arch, []).append(prof)

	# Use an empty profile for checking dependencies of
	# packages that have empty KEYWORDS.
	prof = ProfileDesc('**', 'stable', '', '')
	profiles.setdefault(prof.arch, []).append(prof)
	return profiles


def check_profiles(profiles, archlist):
	for x in archlist:
		if x[0] == "~":
			continue
		if x not in profiles:
			print(red(
				"\"%s\" doesn't have a valid profile listed in profiles.desc." % x))
			print(red(
				"You need to either \"cvs update\" your profiles dir"
				" or follow this"))
			print(red(
				"up with the " + x + " team."))
			print()
