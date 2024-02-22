# Copyright 1999-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import io
import sys

from _emerge.BinpkgFetcher import BinpkgFetcher
from _emerge.CompositeTask import CompositeTask
from _emerge.BinpkgVerifier import BinpkgVerifier
from portage import os


class BinpkgPrefetcher(CompositeTask):
    __slots__ = ("pkg",) + (
        "pkg_path",
        "pkg_allocated_path",
        "_bintree",
    )

    def _start(self):
        self._bintree = self.pkg.root_config.trees["bintree"]
        fetcher = BinpkgFetcher(
            background=self.background,
            logfile=self.scheduler.fetch.log_file,
            pkg=self.pkg,
            scheduler=self.scheduler,
        )
        self.pkg_path = fetcher.pkg_path
        self.pkg_allocated_path = fetcher.pkg_allocated_path
        self._start_task(fetcher, self._fetcher_exit)

    def _fetcher_exit(self, fetcher):
        if self._default_exit(fetcher) != os.EX_OK:
            self.wait()
            return

        verifier = BinpkgVerifier(
            background=self.background,
            logfile=self.scheduler.fetch.log_file,
            pkg=self.pkg,
            scheduler=self.scheduler,
            _pkg_path=self.pkg_path,
        )
        self._start_task(verifier, self._verifier_exit)

    def _verifier_exit(self, verifier):
        if self._default_exit(verifier) != os.EX_OK:
            self.wait()
            return

        stdout_orig = sys.stdout
        stderr_orig = sys.stderr
        out = io.StringIO()
        try:
            sys.stdout = out
            sys.stderr = out

            injected_pkg = self._bintree.inject(
                self.pkg.cpv,
                current_pkg_path=self.pkg_path,
                allocated_pkg_path=self.pkg_allocated_path,
            )

        finally:
            sys.stdout = stdout_orig
            sys.stderr = stderr_orig

            output_value = out.getvalue()
            if output_value:
                self.scheduler.output(
                    output_value,
                    log_path=self.scheduler.fetch.log_file,
                    background=self.background,
                )

        self._current_task = None
        self.returncode = 1 if injected_pkg is None else os.EX_OK
        self.wait()
