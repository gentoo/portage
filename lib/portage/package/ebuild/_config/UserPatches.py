# Copyright 2026 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os

from portage.dep import _slot_separator

# must match filtering done by eapply_user() (see bin/phase-helpers.sh)
_extensions = (".diff", ".patch")

"""
A dict-like object which reflects the user patches in portage config. Keyed by
any type exposing cp, cpv, and (optionally) slot attributes, e.g. _pkg_str,
Atom, Package, etc. The key need not exactly match a userpatch config path.

Use 'in' operator to test for existence of user patches which would be applied
to the corresponding ebuild.

"""


class UserPatches:
    _patch_sets = None

    def __init__(self, abs_user_config):
        patch_dir = os.path.join(abs_user_config, "patches")
        if not os.path.exists(patch_dir):
            return

        categories = os.listdir(patch_dir)
        cpvs = [
            os.path.join(c, p)
            for c in categories
            for p in os.listdir(os.path.join(patch_dir, c))
        ]

        self._patch_sets = {}
        for c in cpvs:
            location = os.path.join(patch_dir, c)
            patch_set = self._load(location)
            if len(patch_set) > 0:
                self._patch_sets[c] = patch_set

    def __contains__(self, key):
        if self._patch_sets is None:
            return False

        if key.cp in self._patch_sets:
            return True
        if key.cpv in self._patch_sets:
            return True

        if hasattr(key.cpv, "slot"):
            slot = _slot_separator + key.cpv.slot
            if key.cp + slot in self._patch_sets:
                return True
            if key.cpv + slot in self._patch_sets:
                return True

        return False

    # load a set of user patches from config directory
    def _load(self, location):
        files = []
        for filename in os.listdir(location):
            if not any(filename.endswith(e) for e in _extensions):
                continue

            # store file basenames as bytes as they need to sort in the same way
            # as "LC_ALL=C sort" would (see phase-helpers.sh)
            files.append(filename.encode())

        return files

    # query using the rules in portage(5) for matching user patches
    def _query(self, func, key):
        result = func(key.cp).copy()  # copy() so as not to mutate
        result |= func(key.cpv)
        if hasattr(key.cpv, "slot"):
            slot = _slot_separator + key.cpv.slot
            result |= func(key.cp + slot)
            result |= func(key.cpv + slot)

        return result

    # return the files that would be applied as user patches
    def patches(self, key, default=set()):
        if not self.__contains__(key):
            return default

        files = lambda x: {
            os.path.join(x, f.decode()) for f in self._patch_sets.get(x, {})
        }

        return self._query(files, key)
