# -*- coding:utf-8 -*-


class DependUnknown(object):

	def __init__(self, **kwargs):
		self.qatracker = kwargs.get('qatracker')

	def check(self, **kwargs):
		ebuild = kwargs.get('ebuild')
		baddepsyntax = kwargs.get('baddepsyntax')
		unknown_pkgs = kwargs.get('unknown_pkgs')

		if not baddepsyntax and unknown_pkgs:
			type_map = {}
			for mytype, atom in unknown_pkgs:
				type_map.setdefault(mytype, set()).add(atom)
			for mytype, atoms in type_map.items():
				self.qatracker.add_error(
					"dependency.unknown", "%s: %s: %s"
					% (ebuild.relative_path, mytype, ", ".join(sorted(atoms))))
		return {'continue': False}

	@property
	def runInPkgs(self):
		return (False, [])

	@property
	def runInEbuilds(self):
		return (True, [self.check])
