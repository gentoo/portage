# -*- coding:utf-8 -*-

from repoman.modules.scan.scanbase import ScanBase


class DependUnknown(ScanBase):
	'''Perform checks to determine unknown dependencies'''

	def __init__(self, **kwargs):
		'''Class init

		@param qatracker: QATracker instance
		'''
		self.qatracker = kwargs.get('qatracker')

	def check(self, **kwargs):
		'''Perform unknown dependancy checks

		@param ebuild: Future.result == Ebuild which we check (object).
		@param baddepsyntax: Future.result == boolean
		@param unknown_pkgs: set of tuples (type, atom.unevaluated_atom)
		@returns: dictionary
		'''
		ebuild = kwargs.get('ebuild').get()
		baddepsyntax = kwargs.get('baddepsyntax').get()
		unknown_pkgs = kwargs.get('unknown_pkgs').get()

		if not baddepsyntax and unknown_pkgs:
			type_map = {}
			for mytype, atom in unknown_pkgs:
				type_map.setdefault(mytype, set()).add(atom)
			for mytype, atoms in type_map.items():
				self.qatracker.add_error(
					"dependency.unknown", "%s: %s: %s"
					% (ebuild.relative_path, mytype, ", ".join(sorted(atoms))))
		return False

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.check])
