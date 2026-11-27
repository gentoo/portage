# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2


from portage.dep import Atom, _repo_separator
from portage.exception import InvalidData


def create_world_atom(pkg, args_set, root_config, before_install=False):
    """Create a new atom for the world file if one does not exist.  If the
    argument atom is precise enough to identify a specific slot then a slot
    atom will be returned. Atoms that are in the system set may also be stored
    in world since a user might want to select multiple slots of a slotted
    package like gcc for example. Unslotted system packages will not be
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
    for cpv in portdb.match(Atom(cp)):
        for repo in repos:
            try:
                available_slots.add(portdb._pkg_str(str(cpv), repo).slot)
            except (KeyError, InvalidData):
                pass

    # If there's only one slot but it's not the de-facto default "0", let's
    # record it anyway given that it's a hint there may be future versions
    # with another slot. But it is indeed a heuristic.
    slotted = len(available_slots) > 1 or (
        len(available_slots) == 1 and "0" not in available_slots
    )

    if slotted and arg_atom.without_repo != cp:
        # If the user gave a specific atom, store it as a
        # slot atom in the world file.
        slot_atom = pkg.slot_atom

        if vardb.match(slot_atom) or before_install:
            # Now verify that the argument is precise
            # enough to identify a specific slot.
            matches = portdb.match(arg_atom)
            matched_slots = set()
            if before_install:
                matched_slots.add(pkg.slot)

            for cpv in matches:
                for repo in repos:
                    try:
                        matched_slots.add(portdb._pkg_str(str(cpv), repo).slot)
                    except (KeyError, InvalidData):
                        pass

            if len(matched_slots) == 1:
                new_world_atom = slot_atom
                if arg_atom.repo:
                    new_world_atom = (
                        str(new_world_atom) + _repo_separator + arg_atom.repo
                    )

    if new_world_atom == sets["selected"].findAtomForPackage(pkg):
        # Both atoms would be identical, so there's nothing to add.
        return None

    if not slotted and not arg_atom.repo:
        # Don't exclude slotted atoms for system packages from world, since
        # a user might want to select multiple slots of a slotted package like
        # gcc for example.
        system_atom = sets["system"].findAtomForPackage(pkg)
        if system_atom:
            if system_atom.category != "virtual":
                return None

            # System virtuals aren't safe to exclude from world since they can
            # match multiple old-style virtuals but only one of them will be
            # pulled in by update or depclean.
            providers = portdb.settings.getvirtuals().get(system_atom.cp)
            if providers and len(providers) == 1 and providers[0].cp == arg_atom.cp:
                return None

    return new_world_atom
