# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.dbapi.vartree import (
    _METADATA_FILE,
    _consolidate_to_metadata_file,
    _explode_metadata_file,
    _read_metadata_file,
)


def _has_usable_metadata(pkgdir):
    """True if pkgdir has a metadata file this portage version can read.

    A file is unusable if its format version is not ours or if the package
    directory has changed since it was written; either way it counts as
    missing and gets rewritten by --fix.
    """
    try:
        return _read_metadata_file(os.path.join(pkgdir, _METADATA_FILE)) is not None
    except OSError:
        return False


def _iter_pkg_dirs(settings):
    """Yield (cpv, package directory) for every installed package."""
    vardb = portage.db[settings.get("EROOT", "/")]["vartree"].dbapi
    for cpv in sorted(vardb.cpv_all()):
        yield cpv, vardb.getpath(cpv)


class VdbMetadata:
    short_desc = "Manage consolidated VDB metadata files"

    @staticmethod
    def name():
        return "vdb"

    def can_progressbar(self, func):
        return False

    def check(self, **kwargs):
        """Report how many packages have/lack the consolidated metadata file."""
        settings = kwargs.get("settings", getattr(portage, "settings", {}))

        with_meta = 0
        without_meta = 0
        for _cpv, pkgdir in _iter_pkg_dirs(settings):
            if _has_usable_metadata(pkgdir):
                with_meta += 1
            else:
                without_meta += 1

        total = with_meta + without_meta
        msgs = [
            f"{total} packages in VDB",
            f"  {with_meta} have consolidated metadata file",
            f"  {without_meta} are missing, stale, or use an older format",
        ]
        if without_meta:
            msgs.append("Run 'emaint vdb --fix' to populate missing metadata files.")
        return (without_meta == 0, msgs if without_meta else None)

    def fix(self, **kwargs):
        """Populate the consolidated metadata file for packages that lack it."""
        settings = kwargs.get("settings", getattr(portage, "settings", {}))
        options = kwargs.get("options") or {}
        delete_individual = options.get("delete_individual_files", False)

        errors = []
        for cpv, pkgdir in _iter_pkg_dirs(settings):
            # _consolidate_to_metadata_file() skips a package whose metadata
            # file is already current, so no check is needed here.
            try:
                _consolidate_to_metadata_file(
                    pkgdir, delete_individual=delete_individual
                )
            except Exception as e:
                errors.append(f"{cpv}: {e}")

        if errors:
            return (False, errors)
        return (True, None)

    def remove(self, **kwargs):
        """Undo --fix: restore individual per-field files, drop the metadata file.

        The reverse of what fix() did, including the --delete-individual-files
        case: a field the metadata file is the only remaining copy of is
        written back to its own file before the metadata file goes away.
        """
        settings = kwargs.get("settings", getattr(portage, "settings", {}))

        errors = []
        restored = 0
        for cpv, pkgdir in _iter_pkg_dirs(settings):
            try:
                restored += len(_explode_metadata_file(pkgdir))
            except Exception as e:
                errors.append(f"{cpv}: {e}")

        if errors:
            return (False, errors)
        if restored:
            return (True, [f"Restored {restored} individual VDB files."])
        return (True, None)
