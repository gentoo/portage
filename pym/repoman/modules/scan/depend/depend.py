# -*- coding:utf-8 -*-


from _emerge.Package import Package

from repoman.check_missingslot import check_missingslot
# import our initialized portage instance
from repoman._portage import portage
from repoman.modules.scan.scanbase import ScanBase
from repoman.qa_data import suspect_virtual, suspect_rdepend


class DependChecks(ScanBase):

	def __init__(self, **kwargs):
		self.qatracker = kwargs.get('qatracker')
		self.portdb = kwargs.get('portdb')

	def check(self, **kwargs):
		ebuild = kwargs.get('ebuild')
		pkg = kwargs.get('pkg')

		unknown_pkgs = set()

		inherited_java_eclass = "java-pkg-2" in ebuild.inherited or \
			"java-pkg-opt-2" in ebuild.inherited,
		inherited_wxwidgets_eclass = "wxwidgets" in ebuild.inherited
		# operator_tokens = set(["||", "(", ")"])
		type_list, badsyntax = [], []
		for mytype in Package._dep_keys + ("LICENSE", "PROPERTIES", "PROVIDE"):
			mydepstr = ebuild.metadata[mytype]

			buildtime = mytype in Package._buildtime_keys
			runtime = mytype in Package._runtime_keys
			token_class = None
			if mytype.endswith("DEPEND"):
				token_class = portage.dep.Atom

			try:
				atoms = portage.dep.use_reduce(
					mydepstr, matchall=1, flat=True,
					is_valid_flag=pkg.iuse.is_valid_flag, token_class=token_class)
			except portage.exception.InvalidDependString as e:
				atoms = None
				badsyntax.append(str(e))

			if atoms and mytype.endswith("DEPEND"):
				if runtime and \
					"test?" in mydepstr.split():
					self.qatracker.add_error(
						mytype + '.suspect',
						"%s: 'test?' USE conditional in %s" %
						(ebuild.relative_path, mytype))

				for atom in atoms:
					if atom == "||":
						continue

					is_blocker = atom.blocker

					# Skip dependency.unknown for blockers, so that we
					# don't encourage people to remove necessary blockers,
					# as discussed in bug 382407. We use atom.without_use
					# due to bug 525376.
					if not is_blocker and \
						not self.portdb.xmatch("match-all", atom.without_use) and \
						not atom.cp.startswith("virtual/"):
						unknown_pkgs.add((mytype, atom.unevaluated_atom))

					if kwargs.get('catdir') != "virtual":
						if not is_blocker and \
							atom.cp in suspect_virtual:
							self.qatracker.add_error(
								'virtual.suspect', ebuild.relative_path +
								": %s: consider using '%s' instead of '%s'" %
								(mytype, suspect_virtual[atom.cp], atom))
						if not is_blocker and \
							atom.cp.startswith("perl-core/"):
							self.qatracker.add_error('dependency.perlcore',
								ebuild.relative_path +
								": %s: please use '%s' instead of '%s'" %
								(mytype,
								atom.replace("perl-core/","virtual/perl-"),
								atom))

					if buildtime and \
						not is_blocker and \
						not inherited_java_eclass and \
						atom.cp == "virtual/jdk":
						self.qatracker.add_error(
							'java.eclassesnotused', ebuild.relative_path)
					elif buildtime and \
						not is_blocker and \
						not inherited_wxwidgets_eclass and \
						atom.cp == "x11-libs/wxGTK":
						self.qatracker.add_error(
							'wxwidgets.eclassnotused',
							"%s: %ss on x11-libs/wxGTK without inheriting"
							" wxwidgets.eclass" % (ebuild.relative_path, mytype))
					elif runtime:
						if not is_blocker and \
							atom.cp in suspect_rdepend:
							self.qatracker.add_error(
								mytype + '.suspect',
								ebuild.relative_path + ": '%s'" % atom)

					if atom.operator == "~" and \
						portage.versions.catpkgsplit(atom.cpv)[3] != "r0":
						qacat = 'dependency.badtilde'
						self.qatracker.add_error(
							qacat, "%s: %s uses the ~ operator"
							" with a non-zero revision: '%s'" %
							(ebuild.relative_path, mytype, atom))

					check_missingslot(atom, mytype, ebuild.eapi, self.portdb, self.qatracker,
						ebuild.relative_path, ebuild.metadata)

			type_list.extend([mytype] * (len(badsyntax) - len(type_list)))

		for m, b in zip(type_list, badsyntax):
			if m.endswith("DEPEND"):
				qacat = "dependency.syntax"
			else:
				qacat = m + ".syntax"
			self.qatracker.add_error(
				qacat, "%s: %s: %s" % (ebuild.relative_path, m, b))

		# data required for some other tests
		badlicsyntax = len([z for z in type_list if z == "LICENSE"])
		badprovsyntax = len([z for z in type_list if z == "PROVIDE"])
		baddepsyntax = len(type_list) != badlicsyntax + badprovsyntax
		badlicsyntax = badlicsyntax > 0
		#badprovsyntax = badprovsyntax > 0

		return {'continue': False, 'unknown_pkgs': unknown_pkgs, 'type_list': type_list,
			'badlicsyntax': badlicsyntax, 'baddepsyntax': baddepsyntax}

	@property
	def runInEbuilds(self):
		return (True, [self.check])
