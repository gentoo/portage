# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.dep import _repo_separator

def create_world_atom(pkg, args_set, root_config):
	"""Create a new atom for the world file if one does not exist.  If the
	argument atom is precise enough to identify a specific slot then a slot
	atom will be returned. Atoms that are in the system set may also be stored
	in world since system atoms can only match one slot while world atoms can
	be greedy with respect to slots.  Unslotted system packages will not be
	stored in world."""

	arg_atom = args_set.findAtomForPackage(pkg)
	if not arg_atom:
		return None
	cp = arg_atom.cp
	new_world_atom = cp
	if arg_atom.repo:
		new_world_atom += _repo_separator + arg_atom.repo
	sets = root_config.sets
	portdb = root_config.trees["porttree"].dbapi
	vardb = root_config.trees["vartree"].dbapi

	if arg_atom.repo is not None:
		repos = [arg_atom.repo]
	else:
		# Iterate over portdbapi.porttrees, since it's common to
		# tweak this attribute in order to adjust match behavior.
		repos = []
		for tree in portdb.porttrees:
			repos.append(portdb.repositories.get_name_for_location(tree))

	available_slots = set()
	for cpv in portdb.match(cp):
		for repo in repos:
			try:
				available_slots.add(portdb.aux_get(cpv, ["SLOT"],
					myrepo=repo)[0])
			except KeyError:
				pass

	slotted = len(available_slots) > 1 or \
		(len(available_slots) == 1 and "0" not in available_slots)
	if not slotted:
		# check the vdb in case this is multislot
		available_slots = set(vardb.aux_get(cpv, ["SLOT"])[0] \
			for cpv in vardb.match(cp))
		slotted = len(available_slots) > 1 or \
			(len(available_slots) == 1 and "0" not in available_slots)
	if slotted and arg_atom.without_repo != cp:
		# If the user gave a specific atom, store it as a
		# slot atom in the world file.
		slot_atom = pkg.slot_atom

		# For USE=multislot, there are a couple of cases to
		# handle here:
		#
		# 1) SLOT="0", but the real SLOT spontaneously changed to some
		#    unknown value, so just record an unslotted atom.
		#
		# 2) SLOT comes from an installed package and there is no
		#    matching SLOT in the portage tree.
		#
		# Make sure that the slot atom is available in either the
		# portdb or the vardb, since otherwise the user certainly
		# doesn't want the SLOT atom recorded in the world file
		# (case 1 above).  If it's only available in the vardb,
		# the user may be trying to prevent a USE=multislot
		# package from being removed by --depclean (case 2 above).

		mydb = portdb
		if not portdb.match(slot_atom):
			# SLOT seems to come from an installed multislot package
			mydb = vardb
		# If there is no installed package matching the SLOT atom,
		# it probably changed SLOT spontaneously due to USE=multislot,
		# so just record an unslotted atom.
		if vardb.match(slot_atom):
			# Now verify that the argument is precise
			# enough to identify a specific slot.
			matches = mydb.match(arg_atom)
			matched_slots = set()
			if mydb is vardb:
				for cpv in matches:
					matched_slots.add(mydb.aux_get(cpv, ["SLOT"])[0])
			else:
				for cpv in matches:
					for repo in repos:
						try:
							matched_slots.add(portdb.aux_get(cpv, ["SLOT"],
								myrepo=repo)[0])
						except KeyError:
							pass

			if len(matched_slots) == 1:
				new_world_atom = slot_atom
				if arg_atom.repo:
					new_world_atom += _repo_separator + arg_atom.repo

	if new_world_atom == sets["selected"].findAtomForPackage(pkg):
		# Both atoms would be identical, so there's nothing to add.
		return None
	if not slotted and not arg_atom.repo:
		# Unlike world atoms, system atoms are not greedy for slots, so they
		# can't be safely excluded from world if they are slotted.
		system_atom = sets["system"].findAtomForPackage(pkg)
		if system_atom:
			if not system_atom.cp.startswith("virtual/"):
				return None
			# System virtuals aren't safe to exclude from world since they can
			# match multiple old-style virtuals but only one of them will be
			# pulled in by update or depclean.
			providers = portdb.settings.getvirtuals().get(system_atom.cp)
			if providers and len(providers) == 1 and \
				providers[0].cp == arg_atom.cp:
				return None
	return new_world_atom

