# Copyright 1999-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import io
import sys

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

        BUILD_ID_TYPE = self.settings.configdict["env"].get("BUILD_ID_TYPE")
        if BUILD_ID_TYPE == "int" or not BUILD_ID_TYPE:
            pkg_allocated_path, build_id = bintree.getname_build_id(
                pkg.cpv, allocate_new=True
            )
        elif BUILD_ID_TYPE == "hash":
            pkg_allocated_path, build_id = bintree._allocate_filename_hash(
                pkg.cpv, os.path.join(self.settings.get("T"), "environment")
            )
        else:
            raise Exception("Invalid BUILD_ID_TYPE")

        bintree._ensure_dir(os.path.dirname(pkg_allocated_path))

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

        stdout_orig = sys.stdout
        stderr_orig = sys.stderr
        out = io.StringIO()
        try:
            sys.stdout = out
            sys.stderr = out

            self._binpkg_info = bintree.inject(
                pkg.cpv,
                current_pkg_path=self._binpkg_tmpfile,
                allocated_pkg_path=self.pkg_allocated_path,
            )

        finally:
            sys.stdout = stdout_orig
            sys.stderr = stderr_orig

            output_value = out.getvalue()
            if output_value:
                self.scheduler.output(
                    output_value,
                    log_path=self.settings.get("PORTAGE_LOG_FILE"),
                    background=self.background,
                )

        self._current_task = None
        self.returncode = 1 if self._binpkg_info is None else os.EX_OK
        self.wait()

    def get_binpkg_info(self):
        return self._binpkg_info
