# Copyright 2026 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os

from portage.dep import _slot_separator
from portage.versions import _pkg_str

# must match filtering done by eapply_user() (see bin/phase-helpers.sh)
_extensions = (".diff", ".patch")


class UserPatches:
    _patches = None

    def __init__(self, abs_user_config):
        patch_dir = os.path.join(abs_user_config, "patches")

        if not os.path.exists(patch_dir):
            return

        categories = os.listdir(patch_dir)
        cpvs = [
            os.path.join(c, d)
            for c in categories
            for d in os.listdir(os.path.join(patch_dir, c))
        ]

        self._patches = {}
        is_patch = lambda f: any(f.endswith(e) for e in _extensions)
        for cpv in cpvs:
            files = os.listdir(os.path.join(patch_dir, cpv))
            if len(files) == 0:
                continue
            self._patches[cpv] = list(filter(is_patch, files))

    def __contains__(self, pkg):
        if self._patches is None:
            return False

        if not isinstance(pkg, _pkg_str):
            raise TypeError(f"expected {_pkg_str}, got {type(pkg)}")

        if pkg.cp in self._patches:
            return True
        if pkg.cpv in self._patches:
            return True

        if hasattr(pkg.cpv, "slot"):
            slot = _slot_separator + pkg.cpv.slot
            if pkg.cp + slot in self._patches:
                return True
            if pkg.cpv + slot in self._patches:
                return True

        return False
