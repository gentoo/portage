# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.dep import Atom
from portage.const import LIBC_PACKAGE_ATOM
from portage.dbapi._expand_new_virt import expand_new_virt

import portage.dbapi.porttree


def find_libc_deps(portdb: portage.dbapi.porttree.dbapi, realized: bool = False):
    """Finds libc package for a ROOT via portdb.

    Parameters
    ----------
    portdb : dbapi
        dbapi instance for portdb (for installed packages).
    realized : bool
        Request installed atoms rather than the installed package satisfying LIBC_PACKAGE_ATOM.

    Returns
    -------
    list
        List of libc packages (or atoms if realized is passed).
    """

    libc_pkgs = set()

    for atom in expand_new_virt(
        portdb,
        LIBC_PACKAGE_ATOM,
    ):
        if atom.blocker:
            continue

        if not realized:
            # Just the raw packages were requested (whatever satifies the virtual)
            libc_pkgs.add(atom)
            continue

        # This will give us something like sys-libs/glibc:2.2, but we want to know
        # what installed atom actually satifies that.
        try:
            libc_pkgs.add(portdb.match(atom)[0])
        except IndexError:
            continue

    return libc_pkgs


def strip_libc_deps(dep_struct: list, libc_deps: set):
    """Strip libc dependency out of a given dependency strucutre.

    Parameters
    ----------
    dep_struct: list
        List of package dependencies (atoms).

    libc_deps: set
        List of dependencies satisfying LIBC_PACKAGE_ATOM to be
        stripped out of any dependencies.

    Returns
    -------
    list
        List of dependencies with any matching libc_deps removed.
    """
    # We're going to just grab the libc provider for ROOT and
    # strip out any dep for the purposes of --changed-deps.
    # We can't go off versions, even though it'd be more precise
    # (see below), because we'd end up with FPs and unnecessary
    # --changed-deps results far too often.
    #
    # This penalizes a bit the case where someone adds a
    # minimum (or maximum) version of libc explicitly in an ebuild
    # without a new revision, but that's extremely rare, and doesn't
    # feel like it changes the balance for what we prefer here.

    for i, x in reversed(list(enumerate(dep_struct))):
        # We only need to bother if x is an Atom because we know the deps
        # we inject are simple & flat.
        if isinstance(x, Atom) and any(x.cp == libc_dep.cp for libc_dep in libc_deps):
            del dep_struct[i]
