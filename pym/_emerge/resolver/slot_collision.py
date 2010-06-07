from __future__ import print_function

from _emerge.AtomArg import AtomArg
from _emerge.PackageArg import PackageArg
from portage.output import colorize
from portage.sets.base import InternalPackageSet
from portage.util import writemsg
from portage.versions import cpv_getversion, vercmp

class slot_conflict_handler(object):
	"""This class keeps track of all slot conflicts and provides
	an interface to get possible solutions.
	"""
	def __init__(self, slot_collision_info, all_parents, myopts):
		self.myopts = myopts
		self.debug = "--debug" in myopts
		if self.debug:
			writemsg("Starting slot conflict handler\n")
		#slot_collision_info is a dict mapping (slot atom, root) to set
		#of packages. The packages in the set all belong to the same
		#slot.
		self.slot_collision_info = slot_collision_info
		
		#A dict mapping packages to pairs of parent package
		#and parent atom
		self.all_parents = all_parents
		
		#set containing all nodes that are part of a slot conflict
		conflict_nodes = set()
		
		#a list containing list of packages that form a slot conflict
		conflict_pkgs = []
		
		#a list containing sets of (parent, atom) pairs that have pulled packages
		#into the same slot
		all_conflict_atoms_by_slotatom = []
		
		#fill conflict_pkgs, all_conflict_atoms_by_slotatom
		for (atom, root), pkgs \
			in slot_collision_info.items():
			conflict_pkgs.append(list(pkgs))
			all_conflict_atoms_by_slotatom.append(set())
			
			for pkg in pkgs:
				conflict_nodes.add(pkg)
				for ppkg, atom in all_parents.get(pkg):
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

		#a list of dicts that hold the needed USE changes to solve all conflicts
		self.solutions = []
		
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
				writemsg("\nNew configuration:\n")
				for pkg in config:
					writemsg("   " + str(pkg) + "\n")
				writemsg("\n")

			new_solutions = self._check_configuration(config, all_conflict_atoms_by_slotatom, conflict_nodes)

			if new_solutions:
				self.solutions.extend(new_solutions)
				if first_config:
					#If the "all ebuild"-config gives a solution, use it.
					#Otherwise enumerate all other soultions.
					if self.debug:
						writemsg("All-ebuild configuration has a solution. Aborting search.\n")
					break
			first_config = False

	def get_conflict(self):
		return "".join(self.conflict_msg)
		
	def _prepare_conflict_msg_and_check_for_specificity(self):
		"""
		Print all slot conflicts in a human readable way.
		"""
		msg = self.conflict_msg
		indent = "  "
		# Max number of parents shown, to avoid flooding the display.
		max_parents = 3
		msg.append("\n!!! Multiple package instances within a single " + \
			"package slot have been pulled\n")
		msg.append("!!! into the dependency graph, resulting" + \
			" in a slot conflict:\n\n")

		for (slot_atom, root), pkgs \
			in self.slot_collision_info.items():
			msg.append(str(slot_atom))
			if root != '/':
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

							if not atom_without_use_set.findAtomForPackage(other_pkg):
								#The version range does not match.
								sub_type = None
								if atom.operator in (">=", ">"):
									sub_type = "ge"
								elif atom.operator in ("=", "~"):
									sub_type = "eq"
								elif atom.operator in ("<=", "<"):
									sub_type = "le"

								atoms = collision_reasons.get(("version", sub_type), set())
								atoms.add((ppkg, atom, other_pkg))
								num_all_specific_atoms += 1
								collision_reasons[("version", sub_type)] = atoms
							elif not atom_set.findAtomForPackage(other_pkg):
								#Use conditionals not met.
								violated_atom = atom.violated_conditionals(other_pkg.use.enabled, ppkg.use.enabled)
								for flag in violated_atom.use.enabled.union(violated_atom.use.disabled):
									atoms = collision_reasons.get(("use", flag), set())
									atoms.add((ppkg, atom, other_pkg))
									collision_reasons[("use", flag)] = atoms
								num_all_specific_atoms += 1

					msg.append(" pulled in by\n")

					selected_for_dispaly = set()

					for (type, sub_type), parents in collision_reasons.items():
						#From each (type, sub_type) pair select at least one atom.
						#Try to select as few atoms as possible

						if type == "version":
							#Find the atom with version that is as far away as possible.
							best_matches = {}
							for ppkg, atom, other_pkg in parents:
								if atom.cp in best_matches:
									cmp = portage.versions.vercmp( \
										portage.versions.cpv_getversion(atom.cpv), \
										portage.versions.cpv_getversion(best_matches[atom.cp][1].cpv))

									if (sub_type == "ge" and  cmp > 0) \
										or (sub_type == "le" and cmp < 0) \
										or (sub_type == "eq" and cmp > 0):
										best_matches[atom.cp] = (ppkg, atom)
								else:
									best_matches[atom.cp] = (ppkg, atom)
							selected_for_dispaly.update(best_matches.values())
						elif type == "use":
							#Prefer atoms with unconditional use deps over, because it's
							#not possible to change them on the parent, which means there
							#are fewer possible solutions.
							use = sub_type
							hard_matches = set()
							conditional_matches = set()
							for ppkg, atom, other_pkg in parents:
								violated_atom = atom.unevaluated_atom.violated_conditionals( \
									other_pkg.use.enabled, ppkg.use.enabled)
								if use in violated_atom.use.enabled.union(violated_atom.use.disabled):
									hard_matches.add((ppkg, atom))
								else:
									conditional_matches.add((ppkg, atom))

							if hard_matches:
								matches = hard_matches
							else:
								matches = conditional_matches
							
							if not selected_for_dispaly.intersection(matches):
								selected_for_dispaly.add(matches.pop())

					def highlight_violations(atom, version, use=[]):
						"""Colorize parts of an atom"""
						atom_str = str(atom)
						if version:
							op = atom.operator
							ver = cpv_getversion(atom.cpv)
							slot = atom.slot
							atom_str = atom_str.replace(op, colorize("BAD", op), 1)
							
							start = atom_str.rfind(ver)
							end = start + len(ver)
							atom_str = atom_str[:start] + \
								colorize("BAD", ver) + \
								atom_str[end+1:]
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

					for parent_atom in selected_for_dispaly:
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
							use = []
							for type, sub_type in collision_reasons:
								if type == "version":
									for x in collision_reasons[(type, sub_type)]:
										if ppkg == x[0] and atom == x[1]:
											version_violated = True
								elif type == "use":
									use.append(sub_type)

							atom_str = highlight_violations(atom.unevaluated_atom, version_violated, use)

							if version_violated:
								self.is_a_version_conflict = True

							msg.append("%s required by %s" % (atom_str, parent))
						msg.append("\n")
					
					if not selected_for_dispaly:
						msg.append(2*indent)
						msg.append("(no parents that aren't satisfied by other packages in this slot)\n")
						self.conflict_is_unspecific = True
					
					omitted_parents = num_all_specific_atoms - len(selected_for_dispaly)
					if omitted_parents:
						msg.append(2*indent)
						if len(selected_for_dispaly) > 1:
							msg.append("(and %d more with the same problems)\n" % omitted_parents)
						else:
							msg.append("(and %d more with the same problem)\n" % omitted_parents)
				else:
					msg.append(" (no parents)\n")
				msg.append("\n")
		msg.append("\n")

	def get_explanation(self):
		msg = ""

		if self.is_a_version_conflict:
			return None

		if self.conflict_is_unspecific and \
			not ("--newuse" in self.myopts and "--update" in self.myopts):
			msg += "!!!Enabling --newuse and --update might solve this conflict.\n"
			msg += "!!!If not, it might at least allow emerge to give a suggestions.\n\n"
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

		def print_solution(solution, indent=""):
			mymsg = ""
			for pkg in solution:
				changes = []
				for flag, state in solution[pkg].items():
					if state == "enabled" and flag not in pkg.use.enabled:
						changes.append(colorize("red", "+" + flag))
					elif state == "disabled" and flag in pkg.use.enabled:
						changes.append(colorize("blue", "-" + flag))
				if changes:
					mymsg += indent + "- " + pkg.cpv + " (Change USE: %s" % " ".join(changes) + ")\n"
			mymsg += "\n"
			return mymsg

		if len(solutions) == 1:
			msg += print_solution(solutions[0], "   ")
		else:
			for solution in solutions:
				msg += "  Solution: Apply all of:\n"
				msg += print_solution(solution, "     ")

		return msg

	def _check_configuration(self, config, all_conflict_atoms_by_slotatom, conflict_nodes):
		"""
		Given a configuartion, required use changes are computed and checked to
		make sure that no new conflict is introduced. Returns a solution or None.
		"""

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
						or pkg.use.enabled.symmetric_difference(other_pkg.use.enabled):
						if self.debug:
							writemsg(str(pkg) + " has pending USE changes. Rejecting configuration.\n")
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
				if i.findAtomForPackage(pkg):
					continue

				i = InternalPackageSet(initial_atoms=(atom.without_use,))
				if not i.findAtomForPackage(pkg):
					#Version range does not match.
					if self.debug:
						writemsg(str(pkg) + " does not satify all version requirements. Rejecting configuration.\n")
					return False

				if not pkg.iuse.is_valid_flag(atom.unevaluated_atom.use.required):
					#Missing IUSE.
					if self.debug:
						writemsg(str(pkg) + " misses need flags from IUSE. Rejecting configuration.\n")
					return False

				if ppkg.installed:
					#We cannot assume that it's possible to reinstall the package. Do not
					#check if some of its atom has use.conditional
					violated_atom = atom.violated_conditionals(pkg.use.enabled, ppkg.use.enabled)
				else:
					violated_atom = atom.unevaluated_atom.violated_conditionals(pkg.use.enabled, ppkg.use.enabled)

				if pkg.installed and (violated_atom.use.enabled or violated_atom.use.disabled):
					#We can't change USE of an installed package (only of an ebuild, but that is already
					#part of the conflict, isn't it?
					if self.debug:
						writemsg(str(pkg) + ": installed package would need USE changes. Rejecting configuration.\n")
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
						if not flag in pkg.use.enabled:
							involved_flags[flag] = "contradiction"
					elif involved_flags[flag] == "disabled":
						if flag in pkg.use.enabled:
							involved_flags[flag] = "contradiction"
					elif involved_flags[flag] == "cond":
						if flag in pkg.use.enabled:
							involved_flags[flag] = "enabled"
						else:
							involved_flags[flag] = "disabled"

			for flag, state in involved_flags.items():
				if state == "contradiction":
					if self.debug:
						writemsg("Contradicting requirements found for flag " + flag + ". Rejecting configuration.\n")
					return False

			all_involved_flags.append(involved_flags)

		if self.debug:
			writemsg("All involved flags:\n")
			for id, involved_flags in enumerate(all_involved_flags):
				writemsg("   " + str(config[id]) + "\n")
				for flag, state in involved_flags.items():
					writemsg("     " + flag + ": " + state + "\n")

		solutions = []
		sol_gen = _solution_candidate_generator(all_involved_flags)
		while(True):
			candidate = sol_gen.get_candidate()
			if not candidate:
				break
			solution = self._check_solution(config, candidate, all_conflict_atoms_by_slotatom)
			if solution:
				solutions.append(solution)
		
		if self.debug:
			if not solutions:
				writemsg("No viable solutions. Rejecting configuration.\n")
		return solutions
		
	
	def _force_flag_for_package(self, required_changes, pkg, flag, state):
		"""
		Adds an USE change to required_changes. Sets the target state to
		"contradiction" if a flag is forced to conflicting values.
		"""
		if state == "disabled":
			changes = required_changes.get(pkg, {})
			flag_change = changes.get(flag, "")
			if flag_change == "enabled":
				flag_change = "contradiction"
			elif flag in pkg.use.enabled:
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
			writemsg(msg)
		
		required_changes = {}
		for id, pkg in enumerate(config):
			if not pkg.installed:
				#We can't change the USE of installed packages.
				for flag in all_involved_flags[id]:
					if not pkg.iuse.is_valid_flag(flag):
						continue
					state = all_involved_flags[id][flag]
					self._force_flag_for_package(required_changes, pkg, flag, state)

			#Go through all (parebt, atom) pairs for the current slot conflict.
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
			if pkg in required_changes:
				old_use = set(pkg.use.enabled)
				new_use = set(pkg.use.enabled)
				use_has_changed = False
				for flag, state in required_changes[pkg].items():
					if state == "enabled" and flag not in new_use:
						new_use.add(flag)
						use_has_changed = True
					elif state == "disabled" and flag in new_use:
						use_has_changed = True
						new_use.remove(flag)
				if use_has_changed:
					new_pkg = pkg.copy()
					new_pkg.metadata["USE"] = " ".join(new_use)
				else:
					new_pkg = pkg
			else:
				new_pkg = pkg

			for ppkg, atom in all_conflict_atoms_by_slotatom[id]:
				if not hasattr(ppkg, "use"):
					#It's a SetArg or something like that.
					continue
				new_use = set(ppkg.use.enabled)
				if ppkg in required_changes:
					for flag, state in required_changes[ppkg].items():
						if state == "enabled" and flag not in new_use:
							new_use.add(flag)
						elif state == "disabled" and flag in new_use:
							new_use.remove(flag)

				new_atom = atom.unevaluated_atom.evaluate_conditionals(new_use)
				i = InternalPackageSet(initial_atoms=(new_atom,))
				if not i.findAtomForPackage(new_pkg):
					#We managed to create a new problem with our changes.
					is_valid_solution = False
					if self.debug:
						writemsg("new conflict introduced: " + str(new_pkg) + \
							" does not match " + new_atom + " from " + str(ppkg) + "\n")
					break

			if not is_valid_solution:
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
		
		
