# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import sys

from _emerge.AtomArg import AtomArg
from _emerge.Package import Package
from _emerge.PackageArg import PackageArg
from portage.dep import check_required_use
from portage.output import colorize
from portage._sets.base import InternalPackageSet
from portage.util import writemsg
from portage.versions import cpv_getversion, vercmp

if sys.hexversion >= 0x3000000:
	basestring = str

class slot_conflict_handler(object):
	"""This class keeps track of all slot conflicts and provides
	an interface to get possible solutions.

	How it works:
	If two packages have been pulled into a slot, one needs to
	go away. This class focuses on cases where this can be achieved
	with a change in USE settings.

	1) Find out if what causes a given slot conflict. There are
	three possibilities:

		a) One parent needs foo-1:0 and another one needs foo-2:0,
		nothing we can do about this. This is called a 'version
		based conflict'.

		b) All parents of one of the conflict packages could use
		another conflict package. This is called an 'unspecific
		conflict'. This should be caught by the backtracking logic.
		Ask the user to enable -uN (if not already enabled). If -uN is
		enabled, this case is treated in the same way as c).

		c) Neither a 'version based conflict' nor an 'unspecific
		conflict'. Ignoring use deps would result result in an
		'unspecific conflict'. This is called a 'specific conflict'.
		This is the only conflict we try to find suggestions for.

	2) Computing suggestions.

	Def.: "configuration": A list of packages, containing exactly one
			package from each slot conflict.

	We try to find USE changes such that all parents of conflict packages
	can work with a package in the configuration we're looking at. This
	is done for all possible configurations, except if the 'all-ebuild'
	configuration has a suggestion. In this case we immediately abort the
	search.
	For the current configuration, all use flags that are part of violated
	use deps are computed. This is done for every slot conflict on its own.

	Def.: "solution (candidate)": An assignment of "enabled" / "disabled"
			values for the use flags that are part of violated use deps.

	Now all involved use flags for the current configuration are known. For
	now they have an undetermined value. Fix their value in the
	following cases:
		* The use dep in the parent atom is unconditional.
		* The parent package is 'installed'.
		* The conflict package is 'installed'.

	USE of 'installed' packages can't be changed. This always requires an
	non-installed package.

	During this procedure, contradictions may occur. In this case the
	configuration has no solution.

	Now generate all possible solution candidates with fixed values. Check
	if they don't introduce new conflicts.

	We have found a valid assignment for all involved use flags. Compute
	the needed USE changes and prepare the message for the user.
	"""

	_check_configuration_max = 1024

	def __init__(self, depgraph):
		self.depgraph = depgraph
		self.myopts = depgraph._frozen_config.myopts
		self.debug = "--debug" in self.myopts
		if self.debug:
			writemsg("Starting slot conflict handler\n", noiselevel=-1)
		#slot_collision_info is a dict mapping (slot atom, root) to set
		#of packages. The packages in the set all belong to the same
		#slot.
		self.slot_collision_info = depgraph._dynamic_config._slot_collision_info
		
		#A dict mapping packages to pairs of parent package
		#and parent atom
		self.all_parents = depgraph._dynamic_config._parent_atoms
		
		#set containing all nodes that are part of a slot conflict
		conflict_nodes = set()
		
		#a list containing list of packages that form a slot conflict
		conflict_pkgs = []
		
		#a list containing sets of (parent, atom) pairs that have pulled packages
		#into the same slot
		all_conflict_atoms_by_slotatom = []
		
		#fill conflict_pkgs, all_conflict_atoms_by_slotatom
		for (atom, root), pkgs \
			in self.slot_collision_info.items():
			conflict_pkgs.append(list(pkgs))
			all_conflict_atoms_by_slotatom.append(set())
			
			for pkg in pkgs:
				conflict_nodes.add(pkg)
				for ppkg, atom in self.all_parents.get(pkg):
					all_conflict_atoms_by_slotatom[-1].add((ppkg, atom))

		#Variable that holds the non-explanation part of the message.
		self.conflict_msg = []
		#If any conflict package was pulled in only by unspecific atoms, then
		#the user forgot to enable --newuse and/or --update.
		self.conflict_is_unspecific = False
		
		#Indicate if the conflict is caused by incompatible version requirements
		#cat/pkg-2 pulled in, but a parent requires <cat/pkg-2
		self.is_a_version_conflict = False

		self._prepare_conflict_msg_and_check_for_specificity()

		#a list of dicts that hold the needed USE values to solve all conflicts
		self.solutions = []

		#a list of dicts that hold the needed USE changes to solve all conflicts
		self.changes = []

		#configuration = a list of packages with exactly one package from every
		#single slot conflict
		config_gen = _configuration_generator(conflict_pkgs)
		first_config = True

		#go through all configurations and collect solutions
		while(True):
			config = config_gen.get_configuration()
			if not config:
				break

			if self.debug:
				writemsg("\nNew configuration:\n", noiselevel=-1)
				for pkg in config:
					writemsg("   " + str(pkg) + "\n", noiselevel=-1)
				writemsg("\n", noiselevel=-1)

			new_solutions = self._check_configuration(config, all_conflict_atoms_by_slotatom, conflict_nodes)

			if new_solutions:
				self.solutions.extend(new_solutions)

				if first_config:
					#If the "all ebuild"-config gives a solution, use it.
					#Otherwise enumerate all other solutions.
					if self.debug:
						writemsg("All-ebuild configuration has a solution. Aborting search.\n", noiselevel=-1)
					break
			first_config = False

			if len(conflict_pkgs) > 4:
				# The number of configurations to check grows exponentially in the number of conflict_pkgs.
				# To prevent excessive running times, only check the "all-ebuild" configuration,
				# if the number of conflict packages is too large.
				if self.debug:
					writemsg("\nAborting search due to excessive number of configurations.\n", noiselevel=-1)
				break

		for solution in self.solutions:
			self._add_change(self._get_change(solution))


	def get_conflict(self):
		return "".join(self.conflict_msg)

	def _is_subset(self, change1, change2):
		"""
		Checks if a set of changes 'change1' is a subset of the changes 'change2'.
		"""
		#All pkgs of change1 have to be in change2.
		#For every package in change1, the changes have to be a subset of
		#the corresponding changes in change2.
		for pkg in change1:
			if pkg not in change2:
				return False

			for flag in change1[pkg]:
				if flag not in change2[pkg]:
					return False
				if change1[pkg][flag] != change2[pkg][flag]:
					return False
		return True

	def _add_change(self, new_change):
		"""
		Make sure to keep only minimal changes. If "+foo", does the job, discard "+foo -bar".
		"""
		changes = self.changes
		#Make sure there is no other solution that is a subset of the new solution.
		ignore = False
		to_be_removed = []
		for change in changes:
			if self._is_subset(change, new_change):
				ignore = True
				break
			elif self._is_subset(new_change, change):
				to_be_removed.append(change)

		if not ignore:
			#Discard all existing change that are a superset of the new change.
			for obsolete_change in to_be_removed:
				changes.remove(obsolete_change)
			changes.append(new_change)

	def _get_change(self, solution):
		_pkg_use_enabled = self.depgraph._pkg_use_enabled
		new_change = {}
		for pkg in solution:
			for flag, state in solution[pkg].items():
				if state == "enabled" and flag not in _pkg_use_enabled(pkg):
					new_change.setdefault(pkg, {})[flag] = True
				elif state == "disabled" and flag in _pkg_use_enabled(pkg):
					new_change.setdefault(pkg, {})[flag] = False
		return new_change

	def _prepare_conflict_msg_and_check_for_specificity(self):
		"""
		Print all slot conflicts in a human readable way.
		"""
		_pkg_use_enabled = self.depgraph._pkg_use_enabled
		msg = self.conflict_msg
		indent = "  "
		msg.append("\n!!! Multiple package instances within a single " + \
			"package slot have been pulled\n")
		msg.append("!!! into the dependency graph, resulting" + \
			" in a slot conflict:\n\n")

		for (slot_atom, root), pkgs \
			in self.slot_collision_info.items():
			msg.append(str(slot_atom))
			if root != self.depgraph._frozen_config._running_root.root:
				msg.append(" for %s" % (root,))
			msg.append("\n\n")

			for pkg in pkgs:
				msg.append(indent)
				msg.append(str(pkg))
				parent_atoms = self.all_parents.get(pkg)
				if parent_atoms:
					#Create a list of collision reasons and map them to sets
					#of atoms.
					#Possible reasons:
					#	("version", "ge") for operator >=, >
					#	("version", "eq") for operator =, ~
					#	("version", "le") for operator <=, <
					#	("use", "<some use flag>") for unmet use conditionals
					collision_reasons = {}
					num_all_specific_atoms = 0

					for ppkg, atom in parent_atoms:
						atom_set = InternalPackageSet(initial_atoms=(atom,))
						atom_without_use_set = InternalPackageSet(initial_atoms=(atom.without_use,))

						for other_pkg in pkgs:
							if other_pkg == pkg:
								continue

							if not atom_without_use_set.findAtomForPackage(other_pkg, \
								modified_use=_pkg_use_enabled(other_pkg)):
								if atom.operator is not None:
									# The version range does not match.
									sub_type = None
									if atom.operator in (">=", ">"):
										sub_type = "ge"
									elif atom.operator in ("=", "~"):
										sub_type = "eq"
									elif atom.operator in ("<=", "<"):
										sub_type = "le"

									key = ("version", sub_type)
									atoms = collision_reasons.get(key, set())
									atoms.add((ppkg, atom, other_pkg))
									num_all_specific_atoms += 1
									collision_reasons[key] = atoms
								else:
									# The sub_slot does not match.
									key = ("sub-slot", atom.sub_slot)
									atoms = collision_reasons.get(key, set())
									atoms.add((ppkg, atom, other_pkg))
									num_all_specific_atoms += 1
									collision_reasons[key] = atoms

							elif not atom_set.findAtomForPackage(other_pkg, \
								modified_use=_pkg_use_enabled(other_pkg)):
								missing_iuse = other_pkg.iuse.get_missing_iuse(
									atom.unevaluated_atom.use.required)
								if missing_iuse:
									for flag in missing_iuse:
										atoms = collision_reasons.get(("use", flag), set())
										atoms.add((ppkg, atom, other_pkg))
										collision_reasons[("use", flag)] = atoms
									num_all_specific_atoms += 1
								else:
									#Use conditionals not met.
									violated_atom = atom.violated_conditionals(_pkg_use_enabled(other_pkg), \
										other_pkg.iuse.is_valid_flag)
									for flag in violated_atom.use.enabled.union(violated_atom.use.disabled):
										atoms = collision_reasons.get(("use", flag), set())
										atoms.add((ppkg, atom, other_pkg))
										collision_reasons[("use", flag)] = atoms
									num_all_specific_atoms += 1

					msg.append(" pulled in by\n")

					selected_for_display = set()
					unconditional_use_deps = set()

					for (type, sub_type), parents in collision_reasons.items():
						#From each (type, sub_type) pair select at least one atom.
						#Try to select as few atoms as possible

						if type == "version":
							#Find the atom with version that is as far away as possible.
							best_matches = {}
							for ppkg, atom, other_pkg in parents:
								if atom.cp in best_matches:
									cmp = vercmp( \
										cpv_getversion(atom.cpv), \
										cpv_getversion(best_matches[atom.cp][1].cpv))

									if (sub_type == "ge" and  cmp > 0) \
										or (sub_type == "le" and cmp < 0) \
										or (sub_type == "eq" and cmp > 0):
										best_matches[atom.cp] = (ppkg, atom)
								else:
									best_matches[atom.cp] = (ppkg, atom)
							selected_for_display.update(best_matches.values())
						elif type == "sub-slot":
							for ppkg, atom, other_pkg in parents:
								selected_for_display.add((ppkg, atom))
						elif type == "use":
							#Prefer atoms with unconditional use deps over, because it's
							#not possible to change them on the parent, which means there
							#are fewer possible solutions.
							use = sub_type
							for ppkg, atom, other_pkg in parents:
								missing_iuse = other_pkg.iuse.get_missing_iuse(
									atom.unevaluated_atom.use.required)
								if missing_iuse:
									unconditional_use_deps.add((ppkg, atom))
								else:
									parent_use = None
									if isinstance(ppkg, Package):
										parent_use = _pkg_use_enabled(ppkg)
									violated_atom = atom.unevaluated_atom.violated_conditionals(
										_pkg_use_enabled(other_pkg),
										other_pkg.iuse.is_valid_flag,
										parent_use=parent_use)
									# It's possible for autounmask to change
									# parent_use such that the unevaluated form
									# of the atom now matches, even though the
									# earlier evaluated form (from before
									# autounmask changed parent_use) does not.
									# In this case (see bug #374423), it's
									# expected that violated_atom.use is None.
									# Since the atom now matches, we don't want
									# to display it in the slot conflict
									# message, so we simply ignore it and rely
									# on the autounmask display to communicate
									# the necessary USE change to the user.
									if violated_atom.use is None:
										continue
									if use in violated_atom.use.enabled or \
										use in violated_atom.use.disabled:
										unconditional_use_deps.add((ppkg, atom))
								# When USE flags are removed, it can be
								# essential to see all broken reverse
								# dependencies here, so don't omit any.
								# If the list is long, people can simply
								# use a pager.
								selected_for_display.add((ppkg, atom))

					def highlight_violations(atom, version, use=[]):
						"""Colorize parts of an atom"""
						atom_str = str(atom)
						if version:
							op = atom.operator
							ver = None
							if atom.cp != atom.cpv:
								ver = cpv_getversion(atom.cpv)
							slot = atom.slot

							if op == "=*":
								op = "="
								ver += "*"

							if op is not None:
								atom_str = atom_str.replace(op, colorize("BAD", op), 1)

							if ver is not None:
								start = atom_str.rfind(ver)
								end = start + len(ver)
								atom_str = atom_str[:start] + \
									colorize("BAD", ver) + \
									atom_str[end:]
							if slot:
								atom_str = atom_str.replace(":" + slot, colorize("BAD", ":" + slot))
						
						if use and atom.use.tokens:
							use_part_start = atom_str.find("[")
							use_part_end = atom_str.find("]")
							
							new_tokens = []
							for token in atom.use.tokens:
								if token.lstrip("-!").rstrip("=?") in use:
									new_tokens.append(colorize("BAD", token))
								else:
									new_tokens.append(token)

							atom_str = atom_str[:use_part_start] \
								+ "[%s]" % (",".join(new_tokens),) + \
								atom_str[use_part_end+1:]
						
						return atom_str

					# Show unconditional use deps first, since those
					# are more problematic than the conditional kind.
					ordered_list = list(unconditional_use_deps)
					if len(selected_for_display) > len(unconditional_use_deps):
						for parent_atom in selected_for_display:
							if parent_atom not in unconditional_use_deps:
								ordered_list.append(parent_atom)
					for parent_atom in ordered_list:
						parent, atom = parent_atom
						msg.append(2*indent)
						if isinstance(parent,
							(PackageArg, AtomArg)):
							# For PackageArg and AtomArg types, it's
							# redundant to display the atom attribute.
							msg.append(str(parent))
						else:
							# Display the specific atom from SetArg or
							# Package types.
							version_violated = False
							sub_slot_violated = False
							use = []
							for (type, sub_type), parents in collision_reasons.items():
								for x in parents:
									if parent == x[0] and atom == x[1]:
										if type == "version":
											version_violated = True
										elif type == "sub-slot":
											sub_slot_violated = True
										elif type == "use":
											use.append(sub_type)
										break

							atom_str = highlight_violations(atom.unevaluated_atom, version_violated, use)

							if version_violated or sub_slot_violated:
								self.is_a_version_conflict = True

							msg.append("%s required by %s" % (atom_str, parent))
						msg.append("\n")
					
					if not selected_for_display:
						msg.append(2*indent)
						msg.append("(no parents that aren't satisfied by other packages in this slot)\n")
						self.conflict_is_unspecific = True
					
					omitted_parents = num_all_specific_atoms - len(selected_for_display)
					if omitted_parents:
						msg.append(2*indent)
						if len(selected_for_display) > 1:
							msg.append("(and %d more with the same problems)\n" % omitted_parents)
						else:
							msg.append("(and %d more with the same problem)\n" % omitted_parents)
				else:
					msg.append(" (no parents)\n")
				msg.append("\n")
		msg.append("\n")

	def get_explanation(self):
		msg = ""
		_pkg_use_enabled = self.depgraph._pkg_use_enabled

		if self.is_a_version_conflict:
			return None

		if self.conflict_is_unspecific and \
			not ("--newuse" in self.myopts and "--update" in self.myopts):
			msg += "!!! Enabling --newuse and --update might solve this conflict.\n"
			msg += "!!! If not, it might help emerge to give a more specific suggestion.\n\n"
			return msg

		solutions = self.solutions
		if not solutions:
			return None

		if len(solutions)==1:
			if len(self.slot_collision_info)==1:
				msg += "It might be possible to solve this slot collision\n"
			else:
				msg += "It might be possible to solve these slot collisions\n"
			msg += "by applying all of the following changes:\n"
		else:
			if len(self.slot_collision_info)==1:
				msg += "It might be possible to solve this slot collision\n"
			else:
				msg += "It might be possible to solve these slot collisions\n"
			msg += "by applying one of the following solutions:\n"

		def print_change(change, indent=""):
			mymsg = ""
			for pkg in change:
				changes = []
				for flag, state in change[pkg].items():
					if state:
						changes.append(colorize("red", "+" + flag))
					else:
						changes.append(colorize("blue", "-" + flag))
				mymsg += indent + "- " + pkg.cpv + " (Change USE: %s" % " ".join(changes) + ")\n"
			mymsg += "\n"
			return mymsg


		if len(self.changes) == 1:
			msg += print_change(self.changes[0], "   ")
		else:
			for change in self.changes:
				msg += "  Solution: Apply all of:\n"
				msg += print_change(change, "     ")

		return msg

	def _check_configuration(self, config, all_conflict_atoms_by_slotatom, conflict_nodes):
		"""
		Given a configuartion, required use changes are computed and checked to
		make sure that no new conflict is introduced. Returns a solution or None.
		"""
		_pkg_use_enabled = self.depgraph._pkg_use_enabled
		#An installed package can only be part of a valid configuration if it has no
		#pending use changed. Otherwise the ebuild will be pulled in again.
		for pkg in config:
			if not pkg.installed:
				continue

			for (atom, root), pkgs \
				in self.slot_collision_info.items():
				if pkg not in pkgs:
					continue
				for other_pkg in pkgs:
					if other_pkg == pkg:
						continue
					if pkg.iuse.all.symmetric_difference(other_pkg.iuse.all) \
						or _pkg_use_enabled(pkg).symmetric_difference(_pkg_use_enabled(other_pkg)):
						if self.debug:
							writemsg(str(pkg) + " has pending USE changes. Rejecting configuration.\n", noiselevel=-1)
						return False

		#A list of dicts. Keeps one dict per slot conflict. [ { flag1: "enabled" }, { flag2: "disabled" } ]
		all_involved_flags = []

		#Go through all slot conflicts
		for id, pkg in enumerate(config):
			involved_flags = {}
			for ppkg, atom in all_conflict_atoms_by_slotatom[id]:
				if ppkg in conflict_nodes and not ppkg in config:
					#The parent is part of a slot conflict itself and is
					#not part of the current config.
					continue

				i = InternalPackageSet(initial_atoms=(atom,))
				if i.findAtomForPackage(pkg, modified_use=_pkg_use_enabled(pkg)):
					continue

				i = InternalPackageSet(initial_atoms=(atom.without_use,))
				if not i.findAtomForPackage(pkg, modified_use=_pkg_use_enabled(pkg)):
					#Version range does not match.
					if self.debug:
						writemsg(str(pkg) + " does not satify all version requirements." + \
							" Rejecting configuration.\n", noiselevel=-1)
					return False

				if not pkg.iuse.is_valid_flag(atom.unevaluated_atom.use.required):
					#Missing IUSE.
					#FIXME: This needs to support use dep defaults.
					if self.debug:
						writemsg(str(pkg) + " misses needed flags from IUSE." + \
							" Rejecting configuration.\n", noiselevel=-1)
					return False

				if not isinstance(ppkg, Package) or ppkg.installed:
					#We cannot assume that it's possible to reinstall the package. Do not
					#check if some of its atom has use.conditional
					violated_atom = atom.violated_conditionals(_pkg_use_enabled(pkg), \
						pkg.iuse.is_valid_flag)
				else:
					violated_atom = atom.unevaluated_atom.violated_conditionals(_pkg_use_enabled(pkg), \
						pkg.iuse.is_valid_flag, parent_use=_pkg_use_enabled(ppkg))
					if violated_atom.use is None:
						# It's possible for autounmask to change
						# parent_use such that the unevaluated form
						# of the atom now matches, even though the
						# earlier evaluated form (from before
						# autounmask changed parent_use) does not.
						# In this case (see bug #374423), it's
						# expected that violated_atom.use is None.
						continue

				if pkg.installed and (violated_atom.use.enabled or violated_atom.use.disabled):
					#We can't change USE of an installed package (only of an ebuild, but that is already
					#part of the conflict, isn't it?
					if self.debug:
						writemsg(str(pkg) + ": installed package would need USE changes." + \
							" Rejecting configuration.\n", noiselevel=-1)
					return False

				#Compute the required USE changes. A flag can be forced to "enabled" or "disabled",
				#it can be in the conditional state "cond" that allows both values or in the
				#"contradiction" state, which means that some atoms insist on differnt values
				#for this flag and those kill this configuration.
				for flag in violated_atom.use.required:
					state = involved_flags.get(flag, "")
					
					if flag in violated_atom.use.enabled:
						if state in ("", "cond", "enabled"):
							state = "enabled"
						else:
							state = "contradiction"
					elif flag in violated_atom.use.disabled:
						if state in ("", "cond", "disabled"):
							state = "disabled"
						else:
							state = "contradiction"
					else:
						if state == "":
							state = "cond"

					involved_flags[flag] = state

			if pkg.installed:
				#We don't change the installed pkg's USE. Force all involved flags
				#to the same value as the installed package has it.
				for flag in involved_flags:
					if involved_flags[flag] == "enabled":
						if not flag in _pkg_use_enabled(pkg):
							involved_flags[flag] = "contradiction"
					elif involved_flags[flag] == "disabled":
						if flag in _pkg_use_enabled(pkg):
							involved_flags[flag] = "contradiction"
					elif involved_flags[flag] == "cond":
						if flag in _pkg_use_enabled(pkg):
							involved_flags[flag] = "enabled"
						else:
							involved_flags[flag] = "disabled"

			for flag, state in involved_flags.items():
				if state == "contradiction":
					if self.debug:
						writemsg("Contradicting requirements found for flag " + \
							flag + ". Rejecting configuration.\n", noiselevel=-1)
					return False

			all_involved_flags.append(involved_flags)

		if self.debug:
			writemsg("All involved flags:\n", noiselevel=-1)
			for id, involved_flags in enumerate(all_involved_flags):
				writemsg("   " + str(config[id]) + "\n", noiselevel=-1)
				for flag, state in involved_flags.items():
					writemsg("     " + flag + ": " + state + "\n", noiselevel=-1)

		solutions = []
		sol_gen = _solution_candidate_generator(all_involved_flags)
		checked = 0
		while True:
			candidate = sol_gen.get_candidate()
			if not candidate:
				break
			solution = self._check_solution(config, candidate, all_conflict_atoms_by_slotatom)
			checked += 1
			if solution:
				solutions.append(solution)

			if checked >= self._check_configuration_max:
				# TODO: Implement early elimination for candidates that would
				# change forced or masked flags, and don't count them here.
				if self.debug:
					writemsg("\nAborting _check_configuration due to "
						"excessive number of candidates.\n", noiselevel=-1)
				break

		if self.debug:
			if not solutions:
				writemsg("No viable solutions. Rejecting configuration.\n", noiselevel=-1)
		return solutions
		
	
	def _force_flag_for_package(self, required_changes, pkg, flag, state):
		"""
		Adds an USE change to required_changes. Sets the target state to
		"contradiction" if a flag is forced to conflicting values.
		"""
		_pkg_use_enabled = self.depgraph._pkg_use_enabled

		if state == "disabled":
			changes = required_changes.get(pkg, {})
			flag_change = changes.get(flag, "")
			if flag_change == "enabled":
				flag_change = "contradiction"
			elif flag in _pkg_use_enabled(pkg):
				flag_change = "disabled"
			
			changes[flag] = flag_change
			required_changes[pkg] = changes
		elif state == "enabled":
			changes = required_changes.get(pkg, {})
			flag_change = changes.get(flag, "")
			if flag_change == "disabled":
				flag_change = "contradiction"
			else:
				flag_change = "enabled"
			
			changes[flag] = flag_change
			required_changes[pkg] = changes
								
	def _check_solution(self, config, all_involved_flags, all_conflict_atoms_by_slotatom):
		"""
		Given a configuartion and all involved flags, all possible settings for the involved
		flags are checked if they solve the slot conflict.
		"""
		_pkg_use_enabled = self.depgraph._pkg_use_enabled

		if self.debug:
			#The code is a bit verbose, because the states might not
			#be a string, but a _value_helper.
			msg = "Solution candidate: "
			msg += "["
			first = True
			for involved_flags in all_involved_flags:
				if first:
					first = False
				else:
					msg += ", "
				msg += "{"
				inner_first = True
				for flag, state in involved_flags.items():
					if inner_first:
						inner_first = False
					else:
						msg += ", "
					msg += flag + ": " + str(state)
				msg += "}"
			msg += "]\n"
			writemsg(msg, noiselevel=-1)
		
		required_changes = {}
		for id, pkg in enumerate(config):
			if not pkg.installed:
				#We can't change the USE of installed packages.
				for flag in all_involved_flags[id]:
					if not pkg.iuse.is_valid_flag(flag):
						continue
					state = all_involved_flags[id][flag]
					self._force_flag_for_package(required_changes, pkg, flag, state)

			#Go through all (parent, atom) pairs for the current slot conflict.
			for ppkg, atom in all_conflict_atoms_by_slotatom[id]:
				use = atom.unevaluated_atom.use
				if not use:
					#No need to force something for an atom without USE conditionals.
					#These atoms are already satisfied.
					continue
				for flag in all_involved_flags[id]:
					state = all_involved_flags[id][flag]
					
					if flag not in use.required or not use.conditional:
						continue
					if flag in use.conditional.enabled:
						#[flag?]
						if state == "enabled":
							#no need to change anything, the atom won't
							#force -flag on pkg
							pass
						elif state == "disabled":
							#if flag is enabled we get [flag] -> it must be disabled
							self._force_flag_for_package(required_changes, ppkg, flag, "disabled")
					elif flag in use.conditional.disabled:
						#[!flag?]
						if state == "enabled":
							#if flag is enabled we get [-flag] -> it must be disabled
							self._force_flag_for_package(required_changes, ppkg, flag, "disabled")
						elif state == "disabled":
							#no need to change anything, the atom won't
							#force +flag on pkg
							pass
					elif flag in use.conditional.equal:
						#[flag=]
						if state == "enabled":
							#if flag is disabled we get [-flag] -> it must be enabled
							self._force_flag_for_package(required_changes, ppkg, flag, "enabled")
						elif state == "disabled":
							#if flag is enabled we get [flag] -> it must be disabled
							self._force_flag_for_package(required_changes, ppkg, flag, "disabled")
					elif flag in use.conditional.not_equal:
						#[!flag=]
						if state == "enabled":
							#if flag is enabled we get [-flag] -> it must be disabled
							self._force_flag_for_package(required_changes, ppkg, flag, "disabled")
						elif state == "disabled":
							#if flag is disabled we get [flag] -> it must be enabled
							self._force_flag_for_package(required_changes, ppkg, flag, "enabled")

		is_valid_solution = True
		for pkg in required_changes:
			for state in required_changes[pkg].values():
				if not state in ("enabled", "disabled"):
					is_valid_solution = False
		
		if not is_valid_solution:
			return None

		#Check if all atoms are satisfied after the changes are applied.
		for id, pkg in enumerate(config):
			new_use = _pkg_use_enabled(pkg)
			if pkg in required_changes:
				old_use = pkg.use.enabled
				new_use = set(new_use)
				for flag, state in required_changes[pkg].items():
					if state == "enabled":
						new_use.add(flag)
					elif state == "disabled":
						new_use.discard(flag)
				if not new_use.symmetric_difference(old_use):
					#avoid copying the package in findAtomForPackage if possible
					new_use = old_use

			for ppkg, atom in all_conflict_atoms_by_slotatom[id]:
				if not hasattr(ppkg, "use"):
					#It's a SetArg or something like that.
					continue
				ppkg_new_use = set(_pkg_use_enabled(ppkg))
				if ppkg in required_changes:
					for flag, state in required_changes[ppkg].items():
						if state == "enabled":
							ppkg_new_use.add(flag)
						elif state == "disabled":
							ppkg_new_use.discard(flag)

				new_atom = atom.unevaluated_atom.evaluate_conditionals(ppkg_new_use)
				i = InternalPackageSet(initial_atoms=(new_atom,))
				if not i.findAtomForPackage(pkg, new_use):
					#We managed to create a new problem with our changes.
					is_valid_solution = False
					if self.debug:
						writemsg("new conflict introduced: " + str(pkg) + \
							" does not match " + new_atom + " from " + str(ppkg) + "\n", noiselevel=-1)
					break

			if not is_valid_solution:
				break

		#Make sure the changes don't violate REQUIRED_USE
		for pkg in required_changes:
			required_use = pkg.metadata.get("REQUIRED_USE")
			if not required_use:
				continue

			use = set(_pkg_use_enabled(pkg))
			for flag, state in required_changes[pkg].items():
				if state == "enabled":
					use.add(flag)
				else:
					use.discard(flag)

			if not check_required_use(required_use, use, pkg.iuse.is_valid_flag):
				is_valid_solution = False
				break

		if is_valid_solution and required_changes:
			return required_changes
		else:
			return None

class _configuration_generator(object):
	def __init__(self, conflict_pkgs):
		#reorder packages such that installed packages come last
		self.conflict_pkgs = []
		for pkgs in conflict_pkgs:
			new_pkgs = []
			for pkg in pkgs:
				if not pkg.installed:
					new_pkgs.append(pkg)
			for pkg in pkgs:
				if pkg.installed:
					new_pkgs.append(pkg)
			self.conflict_pkgs.append(new_pkgs)
			
		self.solution_ids = []
		for pkgs in self.conflict_pkgs:
			self.solution_ids.append(0)
		self._is_first_solution = True
		
	def get_configuration(self):
		if self._is_first_solution:
			self._is_first_solution = False
		else:
			if not self._next():
				return None
		
		solution = []
		for id, pkgs in enumerate(self.conflict_pkgs):
			solution.append(pkgs[self.solution_ids[id]])
		return solution
	
	def _next(self, id=None):
		solution_ids = self.solution_ids
		conflict_pkgs = self.conflict_pkgs
		
		if id is None:
			id = len(solution_ids)-1

		if solution_ids[id] == len(conflict_pkgs[id])-1:
			if id > 0:
				return self._next(id=id-1)
			else:
				return False
		else:
			solution_ids[id] += 1
			for other_id in range(id+1, len(solution_ids)):
				solution_ids[other_id] = 0
			return True

class _solution_candidate_generator(object):
	class _value_helper(object):
		def __init__(self, value=None):
			self.value = value
		def __eq__(self, other):
			if isinstance(other, basestring):
				return self.value == other
			else:
				return self.value == other.value
		def __str__(self):
			return str(self.value)
	
	def __init__(self, all_involved_flags):
		#A copy of all_involved_flags with all "cond" values
		#replaced by a _value_helper object.
		self.all_involved_flags = []
		
		#A list tracking references to all used _value_helper
		#objects.
		self.conditional_values = []
		
		for involved_flags in all_involved_flags:
			new_involved_flags = {}
			for flag, state in involved_flags.items():
				if state in ("enabled", "disabled"):
					new_involved_flags[flag] = state
				else:
					v = self._value_helper("disabled")
					new_involved_flags[flag] = v
					self.conditional_values.append(v)
			self.all_involved_flags.append(new_involved_flags)
			
		self._is_first_solution = True

	def get_candidate(self):
		if self._is_first_solution:
			self._is_first_solution = False
		else:
			if not self._next():
				return None

		return self.all_involved_flags
	
	def _next(self, id=None):
		values = self.conditional_values
		
		if not values:
			return False
		
		if id is None:
			id = len(values)-1

		if values[id].value == "enabled":
			if id > 0:
				return self._next(id=id-1)
			else:
				return False
		else:
			values[id].value = "enabled"
			for other_id in range(id+1, len(values)):
				values[other_id].value = "disabled"
			return True
		
		
