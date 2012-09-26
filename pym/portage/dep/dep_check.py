# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['dep_check', 'dep_eval', 'dep_wordreduce', 'dep_zapdeps']

import logging

import portage
from portage import _unicode_decode
from portage.dep import Atom, match_from_list, use_reduce
from portage.exception import InvalidDependString, ParseError
from portage.localization import _
from portage.util import writemsg, writemsg_level
from portage.versions import vercmp, _pkg_str

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
	expanded to || ( highest match ... lowest match )."""
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
	for x in mysplit:
		if x == "||":
			newsplit.append(x)
			continue
		elif isinstance(x, list):
			newsplit.append(_expand_new_virtuals(x, edebug, mydbapi,
				mysettings, myroot=myroot, trees=trees, use_mask=use_mask,
				use_force=use_force, **kwargs))
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
				# TODO: Add PROVIDE check for repoman.
				a = []
				myvartree = mytrees.get("vartree")
				if myvartree is not None:
					mysettings._populate_treeVirtuals_if_needed(myvartree)
				mychoices = mysettings.getvirtuals().get(mykey, [])
				for y in mychoices:
					a.append(Atom(x.replace(x.cp, y.cp, 1)))
				if not a:
					newsplit.append(x)
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
			depstring = pkg.metadata['RDEPEND']
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
				raise ParseError(_unicode_decode("%s: %s '%s'") % \
					(pkg, mycheck[1], depstring))

			# pull in the new-style virtual
			mycheck[1].append(virt_atom)
			a.append(mycheck[1])
			if atom_graph is not None:
				virt_atom_node = (virt_atom, id(virt_atom))
				atom_graph.add(virt_atom_node, graph_parent)
				atom_graph.add(pkg, virt_atom_node)
		# Plain old-style virtuals.  New-style virtuals are preferred.
		if not pkgs:
				for y in mychoices:
					new_atom = Atom(x.replace(x.cp, y.cp, 1))
					matches = portdb.match(new_atom)
					# portdb is an instance of depgraph._dep_check_composite_db, so
					# USE conditionals are already evaluated.
					if matches and mykey in \
						portdb.aux_get(matches[-1], ['PROVIDE'])[0].split():
						a.append(new_atom)
						if atom_graph is not None:
							atom_graph.add((new_atom, id(new_atom)),
								graph_parent)

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
		elif len(a) == 1:
			newsplit.append(a[0])
		else:
			newsplit.append(['||'] + a)

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
	else:
		for x in deplist:
			if isinstance(x, list):
				if dep_eval(x)==0:
					return 0
			elif x==0 or x==2:
				return 0
		return 1

def dep_zapdeps(unreduced, reduced, myroot, use_binaries=0, trees=None):
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
					use_binaries=use_binaries, trees=trees)
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

	preferred_installed = []
	preferred_in_graph = []
	preferred_any_slot = []
	preferred_non_installed = []
	unsat_use_in_graph = []
	unsat_use_installed = []
	unsat_use_non_installed = []
	other_installed = []
	other_installed_some = []
	other = []

	# unsat_use_* must come after preferred_non_installed
	# for correct ordering in cases like || ( foo[a] foo[b] ).
	choice_bins = (
		preferred_in_graph,
		preferred_installed,
		preferred_any_slot,
		preferred_non_installed,
		unsat_use_in_graph,
		unsat_use_installed,
		unsat_use_non_installed,
		other_installed,
		other_installed_some,
		other,
	)

	# Alias the trees we'll be checking availability against
	parent   = trees[myroot].get("parent")
	priority = trees[myroot].get("priority")
	graph_db = trees[myroot].get("graph_db")
	graph    = trees[myroot].get("graph")
	vardb = None
	if "vartree" in trees[myroot]:
		vardb = trees[myroot]["vartree"].dbapi
	if use_binaries:
		mydbapi = trees[myroot]["bintree"].dbapi
	else:
		mydbapi = trees[myroot]["porttree"].dbapi

	# Sort the deps into installed, not installed but already 
	# in the graph and other, not installed and not in the graph
	# and other, with values of [[required_atom], availablility]
	for x, satisfied in zip(deps, satisfieds):
		if isinstance(x, list):
			atoms = dep_zapdeps(x, satisfied, myroot,
				use_binaries=use_binaries, trees=trees)
		else:
			atoms = [x]
		if vardb is None:
			# When called by repoman, we can simply return the first choice
			# because dep_eval() handles preference selection.
			return atoms

		all_available = True
		all_use_satisfied = True
		slot_map = {}
		cp_map = {}
		for atom in atoms:
			if atom.blocker:
				continue
			# Ignore USE dependencies here since we don't want USE
			# settings to adversely affect || preference evaluation.
			avail_pkg = mydbapi.match(atom.without_use)
			if avail_pkg:
				avail_pkg = avail_pkg[-1] # highest (ascending order)
				avail_pkg = mydbapi._pkg_str(avail_pkg, atom.repo)
				avail_slot = Atom("%s:%s" % (atom.cp, avail_pkg.slot))
			if not avail_pkg:
				all_available = False
				all_use_satisfied = False
				break

			if atom.use:
				avail_pkg_use = mydbapi.match(atom)
				if not avail_pkg_use:
					all_use_satisfied = False
				else:
					# highest (ascending order)
					avail_pkg_use = avail_pkg_use[-1]
					if avail_pkg_use != avail_pkg:
						avail_pkg = avail_pkg_use
					avail_pkg = mydbapi._pkg_str(avail_pkg, atom.repo)
					avail_slot = Atom("%s:%s" % (atom.cp, avail_pkg.slot))

			slot_map[avail_slot] = avail_pkg
			highest_cpv = cp_map.get(avail_pkg.cp)
			if highest_cpv is None or \
				vercmp(avail_pkg.version, highest_cpv.version) > 0:
				cp_map[avail_pkg.cp] = avail_pkg

		this_choice = (atoms, slot_map, cp_map, all_available)
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
					if all_installed_slots:
						unsat_use_installed.append(this_choice)
					else:
						unsat_use_non_installed.append(this_choice)
			else:
				all_in_graph = True
				for slot_atom in slot_map:
					# New-style virtuals have zero cost to install.
					if slot_atom.startswith("virtual/"):
						continue
					# We check if the matched package has actually been
					# added to the digraph, in order to distinguish between
					# those packages and installed packages that may need
					# to be uninstalled in order to resolve blockers.
					graph_matches = graph_db.match_pkgs(slot_atom)
					if not graph_matches or graph_matches[-1] not in graph:
						all_in_graph = False
						break
				circular_atom = None
				if all_in_graph:
					if parent is None or priority is None:
						pass
					elif priority.buildtime and \
						not (priority.satisfied or priority.optional):
						# Check if the atom would result in a direct circular
						# dependency and try to avoid that if it seems likely
						# to be unresolvable. This is only relevant for
						# buildtime deps that aren't already satisfied by an
						# installed package.
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
						if all_in_graph:
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
				other_installed.append(this_choice)
			elif some_installed:
				other_installed_some.append(this_choice)
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
		for choice_1 in choices[1:]:
			atoms_1, slot_map_1, cp_map_1, all_available_1 = choice_1
			cps = set(cp_map_1)
			for choice_2 in choices:
				if choice_1 is choice_2:
					# choice_1 will not be promoted, so move on
					break
				atoms_2, slot_map_2, cp_map_2, all_available_2 = choice_2
				intersecting_cps = cps.intersection(cp_map_2)
				if not intersecting_cps:
					continue
				has_upgrade = False
				has_downgrade = False
				for cp in intersecting_cps:
					version_1 = cp_map_1[cp]
					version_2 = cp_map_2[cp]
					difference = vercmp(version_1.version, version_2.version)
					if difference != 0:
						if difference > 0:
							has_upgrade = True
						else:
							has_downgrade = True
							break
				if has_upgrade and not has_downgrade:
					# promote choice_1 in front of choice_2
					choices.remove(choice_1)
					index_2 = choices.index(choice_2)
					choices.insert(index_2, choice_1)
					break

	for allow_masked in (False, True):
		for choices in choice_bins:
			for atoms, slot_map, cp_map, all_available in choices:
				if all_available or allow_masked:
					return atoms

	assert(False) # This point should not be reachable

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
		mymasks.update(mysettings.usemask)
		mymasks.update(mysettings.archlist())
		mymasks.discard(mysettings["ARCH"])
		useforce.add(mysettings["ARCH"])
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
			eapi = current_parent.metadata['EAPI']

	if isinstance(depstring, list):
		mysplit = depstring
	else:
		try:
			mysplit = use_reduce(depstring, uselist=myusesplit,
			masklist=mymasks, matchall=(use=="all"), excludeall=useforce,
			opconvert=True, token_class=Atom, eapi=eapi)
		except InvalidDependString as e:
			return [0, _unicode_decode("%s") % (e,)]

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
		return [0, _unicode_decode("%s") % (e,)]

	mysplit2=mysplit[:]
	mysplit2=dep_wordreduce(mysplit2,mysettings,mydbapi,mode,use_cache=use_cache)
	if mysplit2 is None:
		return [0, _("Invalid token")]

	writemsg("\n\n\n", 1)
	writemsg("mysplit:  %s\n" % (mysplit), 1)
	writemsg("mysplit2: %s\n" % (mysplit2), 1)

	selected_atoms = dep_zapdeps(mysplit, mysplit2, myroot,
		use_binaries=use_binaries, trees=trees)

	return [1, selected_atoms]

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
