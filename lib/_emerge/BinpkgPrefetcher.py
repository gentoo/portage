# Copyright 1999-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import io
import sys

from _emerge.BinpkgFetcher import BinpkgFetcher
from _emerge.CompositeTask import CompositeTask
from _emerge.BinpkgVerifier import BinpkgVerifier
import portage
from portage import os
from portage.elog import messages as elog_messages
from portage.util import no_color


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

        if self._bintree.get_local_repo_location(self.pkg.cpv):
            os.rename(self.pkg_path, self.pkg_allocated_path)
            self._current_task = None
            self.returncode = os.EX_OK
            self.wait()
            return

        injected_pkg = None
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
                if injected_pkg is None:
                    msg = ["Binary package is not usable:"]
                    msg.extend("\t" + line for line in output_value.splitlines())
                    self._elog("eerror", msg)
                else:
                    self.scheduler.output(
                        output_value,
                        log_path=self.scheduler.fetch.log_file,
                        background=self.background,
                    )

        self._current_task = None
        self.returncode = 1 if injected_pkg is None else os.EX_OK
        self.wait()

    def _elog(self, elog_funcname, lines, phase="other"):
        out = io.StringIO()
        elog_func = getattr(elog_messages, elog_funcname)
        global_havecolor = portage.output.havecolor
        try:
            portage.output.havecolor = not no_color(self._bintree.settings)
            for line in lines:
                elog_func(line, phase=phase, key=self.pkg.cpv, out=out)
        finally:
            portage.output.havecolor = global_havecolor
        msg = out.getvalue()
        if msg:
            self.scheduler.output(
                msg, background=self.background, log_path=self.scheduler.fetch.log_file
            )
