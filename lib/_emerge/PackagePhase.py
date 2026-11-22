# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os

import portage
from portage.util._async.AsyncFunction import AsyncFunction
from portage.util.install_mask import InstallMask, install_mask_dir

from _emerge.CompositeTask import CompositeTask
from _emerge.EbuildProcess import EbuildProcess
from _emerge.SpawnProcess import SpawnProcess


class PackagePhase(CompositeTask):
    """
    Invokes the package phase and handles PKG_INSTALL_MASK.
    """

    __slots__ = (
        "_pkg_install_mask",
        "_proot",
        "actionmap",
        "fd_pipes",
        "logfile",
        "settings",
    )

    _shell_binary = portage.const.BASH_BINARY

    # Recursively copies the directory given by the first parameter to the
    # pathname given by the second, having first removed the latter. If cp(1)
    # is provided by GNU coreutils, regular files shall be hard-linked rather
    # than copied.
    _copy_proot_script = """
        rm -rf -- "${2:?}" || exit
        opts=-pPR
        if cp -l --help >/dev/null 2>&1; then
            opts+=l
        fi
        exec cp "${opts}" -- "$1" "$2"
    """

    def _start(self):
        packdebug_maskstr = ""
        if "packdebug" in self.settings.features:
            # We don't want to include debug information in binpkgs themselves
            # w/ packdebug as binpkg consumers should fetch them via debuginfod.
            packdebug_maskstr += " /usr/src/debug/ /usr/lib/debug/"

        try:
            with open(
                os.path.join(
                    self.settings["PORTAGE_BUILDDIR"],
                    "build-info",
                    "PKG_INSTALL_MASK",
                ),
                encoding="utf-8",
                errors="replace",
            ) as f:
                self._pkg_install_mask = InstallMask(f.read() + packdebug_maskstr)
        except OSError:
            self._pkg_install_mask = InstallMask(packdebug_maskstr)

        if self._pkg_install_mask:
            self._proot = os.path.join(self.settings["T"], "packaging")
            self._start_task(
                SpawnProcess(
                    args=[
                        self._shell_binary,
                        "-c",
                        self._copy_proot_script,
                        self._shell_binary,
                        self.settings["D"],
                        self._proot,
                    ],
                    background=self.background,
                    env=self.settings.environ(),
                    scheduler=self.scheduler,
                    logfile=self.logfile,
                ),
                self._copy_proot_exit,
            )
        else:
            self._proot = self.settings["D"]
            self._start_package_phase()

    def _copy_proot_exit(self, proc):
        if self._default_exit(proc) != os.EX_OK:
            self.wait()
        else:
            self._start_task(
                AsyncFunction(
                    target=install_mask_dir,
                    args=(
                        os.path.join(
                            self._proot, self.settings["EPREFIX"].lstrip(os.sep)
                        ),
                        self._pkg_install_mask,
                    ),
                ),
                self._pkg_install_mask_exit,
            )

    def _pkg_install_mask_exit(self, proc):
        if self._default_exit(proc) != os.EX_OK:
            self.wait()
        else:
            self._start_package_phase()

    def _start_package_phase(self):
        ebuild_process = EbuildProcess(
            actionmap=self.actionmap,
            background=self.background,
            fd_pipes=self.fd_pipes,
            logfile=self.logfile,
            phase="package",
            scheduler=self.scheduler,
            settings=self.settings,
        )

        if self._pkg_install_mask:
            d_orig = self.settings["D"]
            try:
                self.settings["D"] = self._proot
                self._start_task(ebuild_process, self._pkg_install_mask_cleanup)
            finally:
                self.settings["D"] = d_orig
        else:
            self._start_task(ebuild_process, self._default_final_exit)

    def _pkg_install_mask_cleanup(self, proc):
        if self._default_exit(proc) != os.EX_OK:
            self.wait()
        else:
            self._start_task(
                SpawnProcess(
                    args=["rm", "-rf", self._proot],
                    background=self.background,
                    env=self.settings.environ(),
                    scheduler=self.scheduler,
                    logfile=self.logfile,
                ),
                self._default_final_exit,
            )
