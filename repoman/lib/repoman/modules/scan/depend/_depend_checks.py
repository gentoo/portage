# -*- coding:utf-8 -*-

import collections

from _emerge.Package import Package

from portage.dep import Atom

from repoman.check_missingslot import check_missingslot
# import our initialized portage instance
from repoman._portage import portage

def check_slotop(depstr, is_valid_flag, badsyntax, mytype,
	qatracker, relative_path):
	'''Checks if RDEPEND uses ':=' slot operator
	in '||' style dependencies.'''

	try:
		# to find use of ':=' in '||' we preserve
		# tree structure of dependencies
		my_dep_tree = portage.dep.use_reduce(
			depstr,
			flat=False,
			matchall=1,
			is_valid_flag=is_valid_flag,
			opconvert=True,
			token_class=portage.dep.Atom)
	except portage.exception.InvalidDependString as e:
		my_dep_tree = None
		badsyntax.append((mytype, str(e)))

	def _traverse_tree(dep_tree, in_any_of):
		# leaf
		if isinstance(dep_tree, Atom):
			atom = dep_tree
			if in_any_of and atom.slot_operator == '=':
				qatracker.add_error("dependency.badslotop",
					"%s: %s: '%s' uses ':=' slot operator under '||' dep clause." %
					(relative_path, mytype, atom))

		# branches
		if isinstance(dep_tree, list):
			if len(dep_tree) == 0:
				return
			# entering any-of
			if dep_tree[0] == '||':
				_traverse_tree(dep_tree[1:], in_any_of=True)
			else:
				for branch in dep_tree:
					_traverse_tree(branch, in_any_of=in_any_of)
	_traverse_tree(my_dep_tree, False)

def _depend_checks(ebuild, pkg, portdb, qatracker, repo_metadata, qadata):
	'''Checks the ebuild dependencies for errors

	@param pkg: Package in which we check (object).
	@param ebuild: Ebuild which we check (object).
	@param portdb: portdb instance
	@param qatracker: QATracker instance
	@param repo_metadata: dictionary of various repository items.
	@returns: (unknown_pkgs, badlicsyntax)
	'''

	unknown_pkgs = set()

	inherited_java_eclass = ("java-pkg-2" in ebuild.inherited or
		"java-pkg-opt-2" in ebuild.inherited)
	inherited_wxwidgets_eclass = "wxwidgets" in ebuild.inherited
	# operator_tokens = set(["||", "(", ")"])
	badsyntax = []
	for mytype in Package._dep_keys + ("LICENSE", "PROPERTIES"):
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
			badsyntax.append((mytype, str(e)))

		if atoms and mytype.endswith("DEPEND"):
			if runtime and \
				"test?" in mydepstr.split():
				qatracker.add_error(
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
					not portdb.xmatch("match-all", atom.without_use) and \
					not atom.cp.startswith("virtual/"):
					unknown_pkgs.add((mytype, atom.unevaluated_atom))

				if not atom.blocker:
					all_deprecated = False
					for pkg_match in portdb.xmatch("match-all", atom):
						if any(repo_metadata['package.deprecated'].iterAtomsForPackage(pkg_match)):
							all_deprecated = True
						else:
							all_deprecated = False
							break

					if all_deprecated:
						qatracker.add_error(
							'dependency.deprecated',
							ebuild.relative_path + ": '%s'" % atom)

				if pkg.category != "virtual":
					if not is_blocker and \
						atom.cp in qadata.suspect_virtual:
						qatracker.add_error(
							'virtual.suspect', ebuild.relative_path +
							": %s: consider using '%s' instead of '%s'" %
							(mytype, qadata.suspect_virtual[atom.cp], atom))
					if not is_blocker and \
						atom.cp.startswith("perl-core/"):
						qatracker.add_error('dependency.perlcore',
							ebuild.relative_path +
							": %s: please use '%s' instead of '%s'" %
							(mytype,
							atom.replace("perl-core/","virtual/perl-"),
							atom))

				if buildtime and \
					not is_blocker and \
					not inherited_java_eclass and \
					atom.cp == "virtual/jdk":
					qatracker.add_error(
						'java.eclassesnotused', ebuild.relative_path)
				elif buildtime and \
					not is_blocker and \
					not inherited_wxwidgets_eclass and \
					atom.cp == "x11-libs/wxGTK":
					qatracker.add_error(
						'wxwidgets.eclassnotused',
						"%s: %ss on x11-libs/wxGTK without inheriting"
						" wxwidgets.eclass" % (ebuild.relative_path, mytype))
				elif runtime:
					if not is_blocker and \
						atom.cp in qadata.suspect_rdepend:
						qatracker.add_error(
							mytype + '.suspect',
							ebuild.relative_path + ": '%s'" % atom)

				if atom.operator == "~" and \
					portage.versions.catpkgsplit(atom.cpv)[3] != "r0":
					qacat = 'dependency.badtilde'
					qatracker.add_error(
						qacat, "%s: %s uses the ~ operator"
						" with a non-zero revision: '%s'" %
						(ebuild.relative_path, mytype, atom))
				# plain =foo-1.2.3 without revision or *
				if atom.operator == "=" and '-r' not in atom.version:
					qacat = 'dependency.equalsversion'
					qatracker.add_error(
						qacat, "%s: %s uses the = operator with"
						" no revision: '%s'; if any revision is"
						" acceptable, use '~' instead; if only -r0"
						" then please append '-r0' to the dep" %
						(ebuild.relative_path, mytype, atom))

				check_missingslot(atom, mytype, ebuild.eapi, portdb, qatracker,
					ebuild.relative_path, ebuild.metadata)

		if runtime:
			check_slotop(mydepstr, pkg.iuse.is_valid_flag,
				badsyntax, mytype, qatracker, ebuild.relative_path)

	baddepsyntax = False
	dedup = collections.defaultdict(set)
	for m, b in badsyntax:
		if b in dedup[m]:
			continue
		dedup[m].add(b)

		if m.endswith("DEPEND"):
			baddepsyntax = True
			qacat = "dependency.syntax"
		else:
			qacat = m + ".syntax"
		qatracker.add_error(
			qacat, "%s: %s: %s" % (ebuild.relative_path, m, b))

	# Parse the LICENSE variable, remove USE conditions and flatten it.
	licenses = portage.dep.use_reduce(
		ebuild.metadata["LICENSE"], matchall=1, flat=True)

	# Check each entry to ensure that it exists in ${PORTDIR}/licenses/.
	for lic in licenses:
		# Need to check for "||" manually as no portage
		# function will remove it without removing values.
		if lic not in repo_metadata['liclist'] and lic != "||":
			qatracker.add_error("LICENSE.invalid",
				"%s: %s" % (ebuild.relative_path, lic))
		elif lic in repo_metadata['lic_deprecated']:
			qatracker.add_error("LICENSE.deprecated",
				"%s: %s" % (ebuild.relative_path, lic))

	return unknown_pkgs, baddepsyntax
