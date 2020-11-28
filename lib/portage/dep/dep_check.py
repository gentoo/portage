# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ['dep_check', 'dep_eval', 'dep_wordreduce', 'dep_zapdeps']

import collections
import itertools
import logging
import operator

import portage
from portage.dep import Atom, match_from_list, use_reduce
from portage.dep._dnf import (
	dnf_convert as _dnf_convert,
	contains_disjunction as _contains_disjunction,
)
from portage.exception import InvalidDependString, ParseError
from portage.localization import _
from portage.util import writemsg, writemsg_level
from portage.util.digraph import digraph
from portage.util.SlotObject import SlotObject
from portage.versions import vercmp

def _expand_new_virtuals(mysplit, edebug, mydbapi, mysettings, myroot="/",
	trees=None, use_mask=None, use_force=None, **kwargs):
	"""
	In order to solve bug #141118, recursively expand new-style virtuals so
	as to collapse one or more levels of indirection, generating an expanded
	search space. In dep_zapdeps, new-style virtuals will be assigned
	zero cost regardless of whether or not they are currently installed. Virtual
	blockers are supported but only when the virtual expands to a single
	atom because it wouldn't necessarily make sense to block all the components
	of a compound virtual.  When more than one new-style virtual is matched,
	the matches are sorted from highest to lowest versions and the atom is
	expanded to || ( highest match ... lowest match ).

	The result is normalized in the same way as use_reduce, having a top-level
	conjuction, and no redundant nested lists.
	"""
	newsplit = []
	mytrees = trees[myroot]
	portdb = mytrees["porttree"].dbapi
	pkg_use_enabled = mytrees.get("pkg_use_enabled")
	# Atoms are stored in the graph as (atom, id(atom)) tuples
	# since each atom is considered to be a unique entity. For
	# example, atoms that appear identical may behave differently
	# in USE matching, depending on their unevaluated form. Also,
	# specially generated virtual atoms may appear identical while
	# having different _orig_atom attributes.
	atom_graph = mytrees.get("atom_graph")
	parent = mytrees.get("parent")
	virt_parent = mytrees.get("virt_parent")
	graph_parent = None
	if parent is not None:
		if virt_parent is not None:
			graph_parent = virt_parent
			parent = virt_parent
		else:
			graph_parent = parent
	repoman = not mysettings.local_config
	if kwargs["use_binaries"]:
		portdb = trees[myroot]["bintree"].dbapi
	pprovideddict = mysettings.pprovideddict
	myuse = kwargs["myuse"]
	is_disjunction = mysplit and mysplit[0] == '||'
	for x in mysplit:
		if x == "||":
			newsplit.append(x)
			continue
		elif isinstance(x, list):
			assert x, 'Normalization error, empty conjunction found in %s' % (mysplit,)
			if is_disjunction:
				assert x[0] != '||', \
					'Normalization error, nested disjunction found in %s' % (mysplit,)
			else:
				assert x[0] == '||', \
					'Normalization error, nested conjunction found in %s' % (mysplit,)
			x_exp = _expand_new_virtuals(x, edebug, mydbapi,
				mysettings, myroot=myroot, trees=trees, use_mask=use_mask,
				use_force=use_force, **kwargs)
			if is_disjunction:
				if len(x_exp) == 1:
					x = x_exp[0]
					if isinstance(x, list):
						# Due to normalization, a conjunction must not be
						# nested directly in another conjunction, so this
						# must be a disjunction.
						assert x and x[0] == '||', \
							'Normalization error, nested conjunction found in %s' % (x_exp,)
						newsplit.extend(x[1:])
					else:
						newsplit.append(x)
				else:
					newsplit.append(x_exp)
			else:
				newsplit.extend(x_exp)
			continue

		if not isinstance(x, Atom):
			raise ParseError(
				_("invalid token: '%s'") % x)

		if repoman:
			x = x._eval_qa_conditionals(use_mask, use_force)

		mykey = x.cp
		if not mykey.startswith("virtual/"):
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add((x, id(x)), graph_parent)
			continue

		if x.blocker:
			# Virtual blockers are no longer expanded here since
			# the un-expanded virtual atom is more useful for
			# maintaining a cache of blocker atoms.
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add((x, id(x)), graph_parent)
			continue

		if repoman or not hasattr(portdb, 'match_pkgs') or \
			pkg_use_enabled is None:
			if portdb.cp_list(x.cp):
				newsplit.append(x)
			else:
				a = []
				myvartree = mytrees.get("vartree")
				if myvartree is not None:
					mysettings._populate_treeVirtuals_if_needed(myvartree)
				mychoices = mysettings.getvirtuals().get(mykey, [])
				for y in mychoices:
					a.append(Atom(x.replace(x.cp, y.cp, 1)))
				if not a:
					newsplit.append(x)
				elif is_disjunction:
					newsplit.extend(a)
				elif len(a) == 1:
					newsplit.append(a[0])
				else:
					newsplit.append(['||'] + a)
			continue

		pkgs = []
		# Ignore USE deps here, since otherwise we might not
		# get any matches. Choices with correct USE settings
		# will be preferred in dep_zapdeps().
		matches = portdb.match_pkgs(x.without_use)
		# Use descending order to prefer higher versions.
		matches.reverse()
		for pkg in matches:
			# only use new-style matches
			if pkg.cp.startswith("virtual/"):
				pkgs.append(pkg)

		mychoices = []
		if not pkgs and not portdb.cp_list(x.cp):
			myvartree = mytrees.get("vartree")
			if myvartree is not None:
				mysettings._populate_treeVirtuals_if_needed(myvartree)
			mychoices = mysettings.getvirtuals().get(mykey, [])

		if not (pkgs or mychoices):
			# This one couldn't be expanded as a new-style virtual.  Old-style
			# virtuals have already been expanded by dep_virtual, so this one
			# is unavailable and dep_zapdeps will identify it as such.  The
			# atom is not eliminated here since it may still represent a
			# dependency that needs to be satisfied.
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add((x, id(x)), graph_parent)
			continue

		a = []
		for pkg in pkgs:
			virt_atom = '=' + pkg.cpv
			if x.unevaluated_atom.use:
				virt_atom += str(x.unevaluated_atom.use)
				virt_atom = Atom(virt_atom)
				if parent is None:
					if myuse is None:
						virt_atom = virt_atom.evaluate_conditionals(
							mysettings.get("PORTAGE_USE", "").split())
					else:
						virt_atom = virt_atom.evaluate_conditionals(myuse)
				else:
					virt_atom = virt_atom.evaluate_conditionals(
						pkg_use_enabled(parent))
			else:
				virt_atom = Atom(virt_atom)

			# Allow the depgraph to map this atom back to the
			# original, in order to avoid distortion in places
			# like display or conflict resolution code.
			virt_atom.__dict__['_orig_atom'] = x

			# According to GLEP 37, RDEPEND is the only dependency
			# type that is valid for new-style virtuals. Repoman
			# should enforce this.
			depstring = pkg._metadata['RDEPEND']
			pkg_kwargs = kwargs.copy()
			pkg_kwargs["myuse"] = pkg_use_enabled(pkg)
			if edebug:
				writemsg_level(_("Virtual Parent:      %s\n") \
					% (pkg,), noiselevel=-1, level=logging.DEBUG)
				writemsg_level(_("Virtual Depstring:   %s\n") \
					% (depstring,), noiselevel=-1, level=logging.DEBUG)

			# Set EAPI used for validation in dep_check() recursion.
			mytrees["virt_parent"] = pkg

			try:
				mycheck = dep_check(depstring, mydbapi, mysettings,
					myroot=myroot, trees=trees, **pkg_kwargs)
			finally:
				# Restore previous EAPI after recursion.
				if virt_parent is not None:
					mytrees["virt_parent"] = virt_parent
				else:
					del mytrees["virt_parent"]

			if not mycheck[0]:
				raise ParseError("%s: %s '%s'" % \
					(pkg, mycheck[1], depstring))

			# Replace the original atom "x" with "virt_atom" which refers
			# to the specific version of the virtual whose deps we're
			# expanding. The virt_atom._orig_atom attribute is used
			# by depgraph to map virt_atom back to the original atom.
			# We specifically exclude the original atom "x" from the
			# the expanded output here, since otherwise it could trigger
			# incorrect dep_zapdeps behavior (see bug #597752).
			mycheck[1].append(virt_atom)
			a.append(mycheck[1])
			if atom_graph is not None:
				virt_atom_node = (virt_atom, id(virt_atom))
				atom_graph.add(virt_atom_node, graph_parent)
				atom_graph.add(pkg, virt_atom_node)
				atom_graph.add((x, id(x)), graph_parent)

		if not a and mychoices:
			# Check for a virtual package.provided match.
			for y in mychoices:
				new_atom = Atom(x.replace(x.cp, y.cp, 1))
				if match_from_list(new_atom,
					pprovideddict.get(new_atom.cp, [])):
					a.append(new_atom)
					if atom_graph is not None:
						atom_graph.add((new_atom, id(new_atom)), graph_parent)

		if not a:
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add((x, id(x)), graph_parent)
		elif is_disjunction:
			newsplit.extend(a)
		elif len(a) == 1:
			newsplit.extend(a[0])
		else:
			newsplit.append(['||'] + a)

	# For consistency with related functions like use_reduce, always
	# normalize the result to have a top-level conjunction.
	if is_disjunction:
		newsplit = [newsplit]

	return newsplit

def dep_eval(deplist):
	if not deplist:
		return 1
	if deplist[0]=="||":
		#or list; we just need one "1"
		for x in deplist[1:]:
			if isinstance(x, list):
				if dep_eval(x)==1:
					return 1
			elif x==1:
					return 1
		#XXX: unless there's no available atoms in the list
		#in which case we need to assume that everything is
		#okay as some ebuilds are relying on an old bug.
		if len(deplist) == 1:
			return 1
		return 0
	for x in deplist:
		if isinstance(x, list):
			if dep_eval(x)==0:
				return 0
		elif x==0 or x==2:
			return 0
	return 1

class _dep_choice(SlotObject):
	__slots__ = ('atoms', 'slot_map', 'cp_map', 'all_available',
		'all_installed_slots', 'new_slot_count', 'want_update', 'all_in_graph')

def dep_zapdeps(unreduced, reduced, myroot, use_binaries=0, trees=None,
	minimize_slots=False):
	"""
	Takes an unreduced and reduced deplist and removes satisfied dependencies.
	Returned deplist contains steps that must be taken to satisfy dependencies.
	"""
	if trees is None:
		trees = portage.db
	writemsg("ZapDeps -- %s\n" % (use_binaries), 2)
	if not reduced or unreduced == ["||"] or dep_eval(reduced):
		return []

	if unreduced[0] != "||":
		unresolved = []
		for x, satisfied in zip(unreduced, reduced):
			if isinstance(x, list):
				unresolved += dep_zapdeps(x, satisfied, myroot,
					use_binaries=use_binaries, trees=trees,
					minimize_slots=minimize_slots)
			elif not satisfied:
				unresolved.append(x)
		return unresolved

	# We're at a ( || atom ... ) type level and need to make a choice
	deps = unreduced[1:]
	satisfieds = reduced[1:]

	# Our preference order is for an the first item that:
	# a) contains all unmasked packages with the same key as installed packages
	# b) contains all unmasked packages
	# c) contains masked installed packages
	# d) is the first item

	preferred_in_graph = []
	preferred_installed = preferred_in_graph
	preferred_any_slot = preferred_in_graph
	preferred_non_installed = []
	unsat_use_in_graph = []
	unsat_use_installed = []
	unsat_use_non_installed = []
	other_installed = []
	other_installed_some = []
	other_installed_any_slot = []
	other = []

	# unsat_use_* must come after preferred_non_installed
	# for correct ordering in cases like || ( foo[a] foo[b] ).
	choice_bins = (
		preferred_in_graph,
		preferred_non_installed,
		unsat_use_in_graph,
		unsat_use_installed,
		unsat_use_non_installed,
		other_installed,
		other_installed_some,
		other_installed_any_slot,
		other,
	)

	# Alias the trees we'll be checking availability against
	parent   = trees[myroot].get("parent")
	virt_parent = trees[myroot].get("virt_parent")
	priority = trees[myroot].get("priority")
	graph_db = trees[myroot].get("graph_db")
	graph    = trees[myroot].get("graph")
	pkg_use_enabled = trees[myroot].get("pkg_use_enabled")
	graph_interface = trees[myroot].get("graph_interface")
	downgrade_probe = trees[myroot].get("downgrade_probe")
	circular_dependency = trees[myroot].get("circular_dependency")
	vardb = None
	if "vartree" in trees[myroot]:
		vardb = trees[myroot]["vartree"].dbapi
	if use_binaries:
		mydbapi = trees[myroot]["bintree"].dbapi
	else:
		mydbapi = trees[myroot]["porttree"].dbapi

	try:
		mydbapi_match_pkgs = mydbapi.match_pkgs
	except AttributeError:
		def mydbapi_match_pkgs(atom):
			return [mydbapi._pkg_str(cpv, atom.repo)
				for cpv in mydbapi.match(atom)]

	# Sort the deps into installed, not installed but already
	# in the graph and other, not installed and not in the graph
	# and other, with values of [[required_atom], availablility]
	for x, satisfied in zip(deps, satisfieds):
		if isinstance(x, list):
			atoms = dep_zapdeps(x, satisfied, myroot,
				use_binaries=use_binaries, trees=trees,
				minimize_slots=minimize_slots)
		else:
			atoms = [x]
		if vardb is None:
			# When called by repoman, we can simply return the first choice
			# because dep_eval() handles preference selection.
			return atoms

		all_available = True
		all_use_satisfied = True
		all_use_unmasked = True
		conflict_downgrade = False
		installed_downgrade = False
		slot_atoms = collections.defaultdict(list)
		slot_map = {}
		cp_map = {}
		for atom in atoms:
			if atom.blocker:
				continue

			# It's not a downgrade if parent is replacing child.
			replacing = (parent and graph_interface and
				graph_interface.will_replace_child(parent, myroot, atom))
			# Ignore USE dependencies here since we don't want USE
			# settings to adversely affect || preference evaluation.
			avail_pkg = mydbapi_match_pkgs(atom.without_use)
			if not avail_pkg and replacing:
				avail_pkg = [replacing]
			if avail_pkg:
				avail_pkg = avail_pkg[-1] # highest (ascending order)
				avail_slot = Atom("%s:%s" % (atom.cp, avail_pkg.slot))
			if not avail_pkg:
				all_available = False
				all_use_satisfied = False
				break

			if not replacing and graph_db is not None and downgrade_probe is not None:
				slot_matches = graph_db.match_pkgs(avail_slot)
				if (len(slot_matches) > 1 and
					avail_pkg < slot_matches[-1] and
					not downgrade_probe(avail_pkg)):
					# If a downgrade is not desirable, then avoid a
					# choice that pulls in a lower version involved
					# in a slot conflict (bug #531656).
					conflict_downgrade = True

			if atom.use:
				avail_pkg_use = mydbapi_match_pkgs(atom)
				if not avail_pkg_use:
					all_use_satisfied = False

					if pkg_use_enabled is not None:
						# Check which USE flags cause the match to fail,
						# so we can prioritize choices that do not
						# require changes to use.mask or use.force
						# (see bug #515584).
						violated_atom = atom.violated_conditionals(
							pkg_use_enabled(avail_pkg),
							avail_pkg.iuse.is_valid_flag)

						# Note that violated_atom.use can be None here,
						# since evaluation can collapse conditional USE
						# deps that cause the match to fail due to
						# missing IUSE (match uses atom.unevaluated_atom
						# to detect such missing IUSE).
						if violated_atom.use is not None:
							for flag in violated_atom.use.enabled:
								if flag in avail_pkg.use.mask:
									all_use_unmasked = False
									break
							else:
								for flag in violated_atom.use.disabled:
									if flag in avail_pkg.use.force and \
										flag not in avail_pkg.use.mask:
										all_use_unmasked = False
										break
				else:
					# highest (ascending order)
					avail_pkg_use = avail_pkg_use[-1]
					if avail_pkg_use != avail_pkg:
						avail_pkg = avail_pkg_use
					avail_slot = Atom("%s:%s" % (atom.cp, avail_pkg.slot))

			if not replacing and downgrade_probe is not None and graph is not None:
				highest_in_slot = mydbapi_match_pkgs(avail_slot)
				highest_in_slot = (highest_in_slot[-1]
					if highest_in_slot else None)
				if (avail_pkg and highest_in_slot and
					avail_pkg < highest_in_slot and
					not downgrade_probe(avail_pkg) and
					(highest_in_slot.installed or
					highest_in_slot in graph)):
					installed_downgrade = True

			slot_map[avail_slot] = avail_pkg
			slot_atoms[avail_slot].append(atom)
			highest_cpv = cp_map.get(avail_pkg.cp)
			all_match_current = None
			all_match_previous = None
			if (highest_cpv is not None and
				highest_cpv.slot == avail_pkg.slot):
				# If possible, make the package selection internally
				# consistent by choosing a package that satisfies all
				# atoms which match a package in the same slot. Later on,
				# the package version chosen here is used in the
				# has_upgrade/has_downgrade logic to prefer choices with
				# upgrades, and a package choice that is not internally
				# consistent will lead the has_upgrade/has_downgrade logic
				# to produce invalid results (see bug 600346).
				all_match_current = all(a.match(avail_pkg)
					for a in slot_atoms[avail_slot])
				all_match_previous = all(a.match(highest_cpv)
					for a in slot_atoms[avail_slot])
				if all_match_previous and not all_match_current:
					continue

			current_higher = (highest_cpv is None or
				vercmp(avail_pkg.version, highest_cpv.version) > 0)

			if current_higher or (all_match_current and not all_match_previous):
				cp_map[avail_pkg.cp] = avail_pkg

		want_update = False
		if graph_interface is None or graph_interface.removal_action:
			new_slot_count = len(slot_map)
		else:
			new_slot_count = 0
			for slot_atom, avail_pkg in slot_map.items():
				if parent is not None and graph_interface.want_update_pkg(parent, avail_pkg):
					want_update = True
				if (not slot_atom.cp.startswith("virtual/")
					and not graph_db.match_pkgs(slot_atom)):
					new_slot_count += 1

		this_choice = _dep_choice(atoms=atoms, slot_map=slot_map,
			cp_map=cp_map, all_available=all_available,
			all_installed_slots=False,
			new_slot_count=new_slot_count,
			all_in_graph=False,
			want_update=want_update)
		if all_available:
			# The "all installed" criterion is not version or slot specific.
			# If any version of a package is already in the graph then we
			# assume that it is preferred over other possible packages choices.
			all_installed = True
			for atom in set(Atom(atom.cp) for atom in atoms \
				if not atom.blocker):
				# New-style virtuals have zero cost to install.
				if not vardb.match(atom) and not atom.startswith("virtual/"):
					all_installed = False
					break
			all_installed_slots = False
			if all_installed:
				all_installed_slots = True
				for slot_atom in slot_map:
					# New-style virtuals have zero cost to install.
					if not vardb.match(slot_atom) and \
						not slot_atom.startswith("virtual/"):
						all_installed_slots = False
						break
			this_choice.all_installed_slots = all_installed_slots
			if graph_db is None:
				if all_use_satisfied:
					if all_installed:
						if all_installed_slots:
							preferred_installed.append(this_choice)
						else:
							preferred_any_slot.append(this_choice)
					else:
						preferred_non_installed.append(this_choice)
				else:
					if not all_use_unmasked:
						other.append(this_choice)
					elif all_installed_slots:
						unsat_use_installed.append(this_choice)
					else:
						unsat_use_non_installed.append(this_choice)
			elif conflict_downgrade or installed_downgrade:
				other.append(this_choice)
			else:
				all_in_graph = True
				for atom in atoms:
					# New-style virtuals have zero cost to install.
					if atom.blocker or atom.cp.startswith("virtual/"):
						continue
					# We check if the matched package has actually been
					# added to the digraph, in order to distinguish between
					# those packages and installed packages that may need
					# to be uninstalled in order to resolve blockers.
					if not any(pkg in graph for pkg in
						graph_db.match_pkgs(atom)):
						all_in_graph = False
						break
				this_choice.all_in_graph = all_in_graph

				circular_atom = None
				if parent and parent.onlydeps:
						# Check if the atom would result in a direct circular
						# dependency and avoid that for --onlydeps arguments
						# since it can defeat the purpose of --onlydeps.
						# This check should only be used for --onlydeps
						# arguments, since it can interfere with circular
						# dependency backtracking choices, causing the test
						# case for bug 756961 to fail.
						cpv_slot_list = [parent]
						for atom in atoms:
							if atom.blocker:
								continue
							if vardb.match(atom):
								# If the atom is satisfied by an installed
								# version then it's not a circular dep.
								continue
							if atom.cp != parent.cp:
								continue
							if match_from_list(atom, cpv_slot_list):
								circular_atom = atom
								break
				if circular_atom is None and circular_dependency is not None:
					for circular_child in itertools.chain(
								circular_dependency.get(parent, []),
								circular_dependency.get(virt_parent, [])):
								for atom in atoms:
									if not atom.blocker and atom.match(circular_child):
										circular_atom = atom
										break
								if circular_atom is not None:
									break

				if circular_atom is not None:
					other.append(this_choice)
				else:
					if all_use_satisfied:
						if all_in_graph:
							preferred_in_graph.append(this_choice)
						elif all_installed:
							if all_installed_slots:
								preferred_installed.append(this_choice)
							else:
								preferred_any_slot.append(this_choice)
						else:
							preferred_non_installed.append(this_choice)
					else:
						if not all_use_unmasked:
							other.append(this_choice)
						elif all_in_graph:
							unsat_use_in_graph.append(this_choice)
						elif all_installed_slots:
							unsat_use_installed.append(this_choice)
						else:
							unsat_use_non_installed.append(this_choice)
		else:
			all_installed = True
			some_installed = False
			for atom in atoms:
				if not atom.blocker:
					if vardb.match(atom):
						some_installed = True
					else:
						all_installed = False

			if all_installed:
				this_choice.all_installed_slots = True
				other_installed.append(this_choice)
			elif some_installed:
				other_installed_some.append(this_choice)

			# Use Atom(atom.cp) for a somewhat "fuzzy" match, since
			# the whole atom may be too specific. For example, see
			# bug #522652, where using the whole atom leads to an
			# unsatisfiable choice.
			elif any(vardb.match(Atom(atom.cp)) for atom in atoms
				if not atom.blocker):
				other_installed_any_slot.append(this_choice)
			else:
				other.append(this_choice)

	# Prefer choices which contain upgrades to higher slots. This helps
	# for deps such as || ( foo:1 foo:2 ), where we want to prefer the
	# atom which matches the higher version rather than the atom furthest
	# to the left. Sorting is done separately for each of choice_bins, so
	# as not to interfere with the ordering of the bins. Because of the
	# bin separation, the main function of this code is to allow
	# --depclean to remove old slots (rather than to pull in new slots).
	for choices in choice_bins:
		if len(choices) < 2:
			continue

		if minimize_slots:
			# Prefer choices having fewer new slots. When used with DNF form,
			# this can eliminate unecessary packages that depclean would
			# ultimately eliminate (see bug 632026). Only use this behavior
			# when deemed necessary by the caller, since this will discard the
			# order specified in the ebuild, and the preferences specified
			# there can serve as a crucial sources of guidance (see bug 645002).

			# NOTE: Under some conditions, new_slot_count value may have some
			# variance from one calculation to the next because it depends on
			# the order that packages are added to the graph. This variance can
			# contribute to outcomes that appear to be random. Meanwhile,
			# the order specified in the ebuild is without variance, so it
			# does not have this problem.
			choices.sort(key=operator.attrgetter('new_slot_count'))

		for choice_1 in choices[1:]:
			cps = set(choice_1.cp_map)
			for choice_2 in choices:
				if choice_1 is choice_2:
					# choice_1 will not be promoted, so move on
					break
				if (
					# Prefer choices where all_installed_slots is True, except
					# in cases where we want to upgrade to a new slot as in
					# bug 706278. Don't compare new_slot_count here since that
					# would aggressively override the preference order defined
					# in the ebuild, breaking the test case for bug 645002.
					(choice_1.all_installed_slots and
					not choice_2.all_installed_slots and
					not choice_2.want_update)
				):
					# promote choice_1 in front of choice_2
					choices.remove(choice_1)
					index_2 = choices.index(choice_2)
					choices.insert(index_2, choice_1)
					break

				intersecting_cps = cps.intersection(choice_2.cp_map)
				has_upgrade = False
				has_downgrade = False
				for cp in intersecting_cps:
					version_1 = choice_1.cp_map[cp]
					version_2 = choice_2.cp_map[cp]
					difference = vercmp(version_1.version, version_2.version)
					if difference != 0:
						if difference > 0:
							has_upgrade = True
						else:
							has_downgrade = True

				if (
					# Prefer upgrades.
					(has_upgrade and not has_downgrade)

					# Prefer choices where all packages have been pulled into
					# the graph, except for choices that eliminate upgrades.
					or (choice_1.all_in_graph and not choice_2.all_in_graph and
					not (has_downgrade and not has_upgrade))
				):
					# promote choice_1 in front of choice_2
					choices.remove(choice_1)
					index_2 = choices.index(choice_2)
					choices.insert(index_2, choice_1)
					break

	for allow_masked in (False, True):
		for choices in choice_bins:
			for choice in choices:
				if choice.all_available or allow_masked:
					return choice.atoms

	assert False # This point should not be reachable

def dep_check(depstring, mydbapi, mysettings, use="yes", mode=None, myuse=None,
	use_cache=1, use_binaries=0, myroot=None, trees=None):
	"""
	Takes a depend string, parses it, and selects atoms.
	The myroot parameter is unused (use mysettings['EROOT'] instead).
	"""
	myroot = mysettings['EROOT']
	edebug = mysettings.get("PORTAGE_DEBUG", None) == "1"
	#check_config_instance(mysettings)
	if trees is None:
		trees = globals()["db"]
	if use=="yes":
		if myuse is None:
			#default behavior
			myusesplit = mysettings["PORTAGE_USE"].split()
		else:
			myusesplit = myuse
			# We've been given useflags to use.
			#print "USE FLAGS PASSED IN."
			#print myuse
			#if "bindist" in myusesplit:
			#	print "BINDIST is set!"
			#else:
			#	print "BINDIST NOT set."
	else:
		#we are being run by autouse(), don't consult USE vars yet.
		# WE ALSO CANNOT USE SETTINGS
		myusesplit=[]

	mymasks = set()
	useforce = set()
	if use == "all":
		# This is only for repoman, in order to constrain the use_reduce
		# matchall behavior to account for profile use.mask/force. The
		# ARCH/archlist code here may be redundant, since the profile
		# really should be handling ARCH masking/forcing itself.
		arch = mysettings.get("ARCH")
		mymasks.update(mysettings.usemask)
		mymasks.update(mysettings.archlist())
		if arch:
			mymasks.discard(arch)
			useforce.add(arch)
		useforce.update(mysettings.useforce)
		useforce.difference_update(mymasks)

	# eapi code borrowed from _expand_new_virtuals()
	mytrees = trees[myroot]
	parent = mytrees.get("parent")
	virt_parent = mytrees.get("virt_parent")
	current_parent = None
	eapi = None
	if parent is not None:
		if virt_parent is not None:
			current_parent = virt_parent
		else:
			current_parent = parent

	if current_parent is not None:
		# Don't pass the eapi argument to use_reduce() for installed packages
		# since previous validation will have already marked them as invalid
		# when necessary and now we're more interested in evaluating
		# dependencies so that things like --depclean work as well as possible
		# in spite of partial invalidity.
		if not current_parent.installed:
			eapi = current_parent.eapi

	if isinstance(depstring, list):
		mysplit = depstring
	else:
		try:
			mysplit = use_reduce(depstring, uselist=myusesplit,
				masklist=mymasks, matchall=(use=="all"), excludeall=useforce,
				opconvert=True, token_class=Atom, eapi=eapi)
		except InvalidDependString as e:
			return [0, "%s" % (e,)]

	if mysplit == []:
		#dependencies were reduced to nothing
		return [1,[]]

	# Recursively expand new-style virtuals so as to
	# collapse one or more levels of indirection.
	try:
		mysplit = _expand_new_virtuals(mysplit, edebug, mydbapi, mysettings,
			use=use, mode=mode, myuse=myuse,
			use_force=useforce, use_mask=mymasks, use_cache=use_cache,
			use_binaries=use_binaries, myroot=myroot, trees=trees)
	except ParseError as e:
		return [0, "%s" % (e,)]

	dnf = False
	if mysettings.local_config: # if not repoman
		orig_split = mysplit
		mysplit = _overlap_dnf(mysplit)
		dnf = mysplit is not orig_split

	mysplit2 = dep_wordreduce(mysplit,
		mysettings, mydbapi, mode, use_cache=use_cache)
	if mysplit2 is None:
		return [0, _("Invalid token")]

	writemsg("\n\n\n", 1)
	writemsg("mysplit:  %s\n" % (mysplit), 1)
	writemsg("mysplit2: %s\n" % (mysplit2), 1)

	selected_atoms = dep_zapdeps(mysplit, mysplit2, myroot,
		use_binaries=use_binaries, trees=trees, minimize_slots=dnf)

	return [1, selected_atoms]


def _overlap_dnf(dep_struct):
	"""
	Combine overlapping || groups using disjunctive normal form (DNF), in
	order to minimize the number of packages chosen to satisfy cases like
	"|| ( foo bar ) || ( bar baz )" as in bug #632026. Non-overlapping
	groups are excluded from the conversion, since DNF leads to exponential
	explosion of the formula.

	When dep_struct does not contain any overlapping groups, no DNF
	conversion will be performed, and dep_struct will be returned as-is.
	Callers can detect this case by checking if the returned object has
	the same identity as dep_struct. If the identity is different, then
	DNF conversion was performed.
	"""
	if not _contains_disjunction(dep_struct):
		return dep_struct

	# map atom.cp to disjunctions
	cp_map = collections.defaultdict(list)
	# graph atom.cp, with edges connecting atoms in the same disjunction
	overlap_graph = digraph()
	# map id(disjunction) to index in dep_struct, for deterministic output
	order_map = {}
	order_key = lambda x: order_map[id(x)]
	result = []
	for i, x in enumerate(dep_struct):
		if isinstance(x, list):
			assert x and x[0] == '||', \
				'Normalization error, nested conjunction found in %s' % (dep_struct,)
			order_map[id(x)] = i
			prev_cp = None
			for atom in _iter_flatten(x):
				if isinstance(atom, Atom) and not atom.blocker:
					cp_map[atom.cp].append(x)
					overlap_graph.add(atom.cp, parent=prev_cp)
					prev_cp = atom.cp
			if prev_cp is None: # only contains blockers
				result.append(x)
		else:
			result.append(x)

	# group together disjunctions having atom.cp overlap
	traversed = set()
	overlap = False
	for cp in overlap_graph:
		if cp in traversed:
			continue
		disjunctions = {}
		stack = [cp]
		while stack:
			cp = stack.pop()
			traversed.add(cp)
			for x in cp_map[cp]:
				disjunctions[id(x)] = x
			for other_cp in itertools.chain(overlap_graph.child_nodes(cp),
				overlap_graph.parent_nodes(cp)):
				if other_cp not in traversed:
					stack.append(other_cp)

		if len(disjunctions) > 1:
			overlap = True
			# convert overlapping disjunctions to DNF
			result.extend(_dnf_convert(
				sorted(disjunctions.values(), key=order_key)))
		else:
			# pass through non-overlapping disjunctions
			result.append(disjunctions.popitem()[1])

	return result if overlap else dep_struct


def _iter_flatten(dep_struct):
	"""
	Yield nested elements of dep_struct.
	"""
	for x in dep_struct:
		if isinstance(x, list):
			for x in _iter_flatten(x):
				yield x
		else:
			yield x


def dep_wordreduce(mydeplist,mysettings,mydbapi,mode,use_cache=1):
	"Reduces the deplist to ones and zeros"
	deplist=mydeplist[:]
	for mypos, token in enumerate(deplist):
		if isinstance(deplist[mypos], list):
			#recurse
			deplist[mypos]=dep_wordreduce(deplist[mypos],mysettings,mydbapi,mode,use_cache=use_cache)
		elif deplist[mypos]=="||":
			pass
		elif token[:1] == "!":
			deplist[mypos] = False
		else:
			mykey = deplist[mypos].cp
			if mysettings and mykey in mysettings.pprovideddict and \
			        match_from_list(deplist[mypos], mysettings.pprovideddict[mykey]):
				deplist[mypos]=True
			elif mydbapi is None:
				# Assume nothing is satisfied.  This forces dep_zapdeps to
				# return all of deps the deps that have been selected
				# (excluding those satisfied by package.provided).
				deplist[mypos] = False
			else:
				if mode:
					x = mydbapi.xmatch(mode, deplist[mypos])
					if mode.startswith("minimum-"):
						mydep = []
						if x:
							mydep.append(x)
					else:
						mydep = x
				else:
					mydep=mydbapi.match(deplist[mypos],use_cache=use_cache)
				if mydep!=None:
					tmp=(len(mydep)>=1)
					if deplist[mypos][0]=="!":
						tmp=False
					deplist[mypos]=tmp
				else:
					#encountered invalid string
					return None
	return deplist
