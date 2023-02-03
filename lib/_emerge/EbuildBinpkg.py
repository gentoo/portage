# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.CompositeTask import CompositeTask
from _emerge.EbuildPhase import EbuildPhase

import portage
from portage import os


class EbuildBinpkg(CompositeTask):
    """
    This assumes that src_install() has successfully completed.
    """

    __slots__ = ("pkg", "settings") + (
        "_binpkg_tmpfile",
        "_binpkg_info",
        "pkg_allocated_path",
    )

    def _start(self):
        pkg = self.pkg
        root_config = pkg.root_config
        bintree = root_config.trees["bintree"]
        pkg_allocated_path, build_id = bintree.getname_build_id(
            pkg.cpv, allocate_new=True
        )

        self.pkg_allocated_path = pkg_allocated_path
        self._binpkg_tmpfile = self.pkg_allocated_path + "." + str(portage.getpid())
        self.settings["PORTAGE_BINPKG_TMPFILE"] = self._binpkg_tmpfile

        if "binpkg-multi-instance" in self.settings.features:
            self.settings["BUILD_ID"] = str(build_id)

        package_phase = EbuildPhase(
            background=self.background,
            phase="package",
            scheduler=self.scheduler,
            settings=self.settings,
        )

        self._start_task(package_phase, self._package_phase_exit)

    def _package_phase_exit(self, package_phase):
        self.settings.pop("PORTAGE_BINPKG_TMPFILE", None)
        if self._default_exit(package_phase) != os.EX_OK:
            try:
                os.unlink(self._binpkg_tmpfile)
            except OSError:
                pass
            self.wait()
            return

        pkg = self.pkg
        bintree = pkg.root_config.trees["bintree"]
        self._binpkg_info = bintree.inject(
            pkg.cpv,
            current_pkg_path=self._binpkg_tmpfile,
            allocated_pkg_path=self.pkg_allocated_path,
        )

        self._current_task = None
        self.returncode = os.EX_OK
        self.wait()

    def get_binpkg_info(self):
        return self._binpkg_info
