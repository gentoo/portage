

class ProfileDesc(object):
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


def dev_keywords(profiles):
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

