# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import re
import subprocess
import sys
import textwrap

import portage
from portage.const import (
    PORTAGE_PYM_PATH,
    USER_CONFIG_PATH,
)
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs

# Each pkg_pretend records the time it started and finished, so that the
# test can tell whether the phases overlapped. The sleep has to be long
# enough that all of the jobs are guaranteed to overlap on a slow machine.
PRETEND_SLEEP = 5

MISC_CONTENT = textwrap.dedent(f"""
    S="${{WORKDIR}}"

    pkg_pretend() {{
        einfo "PRETEND-BEGIN ${{PN}} $(date +%s.%N)"
        einfo "PRETEND-BODY ${{PN}}"
        sleep {PRETEND_SLEEP}
        einfo "PRETEND-END ${{PN}} $(date +%s.%N)"
    }}
    """)

FAILING_MISC_CONTENT = textwrap.dedent("""
    S="${WORKDIR}"

    pkg_pretend() {
        eerror "PRETEND-FAIL ${PN}"
        die "pkg_pretend failed on purpose"
    }
    """)

MARKER_RE = re.compile(r"PRETEND-(BEGIN|BODY|END) (\w+)(?: (\d+\.\d+))?")


class PkgPretendTestCase(TestCase):
    def _playground_env(self, playground):
        settings = playground.settings
        eprefix = settings["EPREFIX"]

        portage_python = portage._python_interpreter
        emerge_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(self.bindir), "emerge"),
            "--oneshot",
        )

        pythonpath = os.environ.get("PYTHONPATH")
        if pythonpath is not None and not pythonpath.strip():
            pythonpath = None
        if pythonpath is not None and pythonpath.split(":")[0] == PORTAGE_PYM_PATH:
            pass
        else:
            if pythonpath is None:
                pythonpath = ""
            else:
                pythonpath = ":" + pythonpath
            pythonpath = PORTAGE_PYM_PATH + pythonpath

        env = {
            "PORTAGE_OVERRIDE_EPREFIX": eprefix,
            "PATH": settings.get("PATH"),
            "PORTAGE_PYTHON": portage_python,
            "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
            "PYTHONPATH": pythonpath,
            "PORTAGE_INST_GID": str(os.getgid()),
            "PORTAGE_INST_UID": str(os.getuid()),
        }

        dirs = [
            playground.distdir,
            os.path.join(eprefix, "var", "tmp", "portage"),
            os.path.join(eprefix, USER_CONFIG_PATH),
            os.path.join(eprefix, "var", "cache", "edb"),
        ]
        for d in dirs:
            ensure_dirs(d)

        with open(os.path.join(eprefix, "var", "cache", "edb", "counter"), "wb") as f:
            f.write(b"100")

        return emerge_cmd, env

    def _run_emerge(self, emerge_cmd, env, args):
        proc = subprocess.Popen(
            emerge_cmd + args,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output = proc.communicate()[0].decode("utf-8", "replace")
        return proc.returncode, output

    def _parse_markers(self, output):
        """
        Return the ordered list of (kind, pn, timestamp) markers found in
        the given emerge output.
        """
        markers = []
        for line in output.splitlines():
            match = MARKER_RE.search(line)
            if match is not None:
                kind, pn, timestamp = match.groups()
                markers.append(
                    (kind, pn, None if timestamp is None else float(timestamp))
                )
        return markers

    def _assert_not_interleaved(self, markers, pns):
        """
        Assert that each package emitted BEGIN, BODY and END consecutively,
        with no output from another package in between.
        """
        self.assertEqual(len(markers), 3 * len(pns), f"unexpected markers: {markers}")
        seen = []
        for i in range(0, len(markers), 3):
            block = markers[i : i + 3]
            self.assertEqual(
                [kind for kind, _, _ in block],
                ["BEGIN", "BODY", "END"],
                f"markers out of order: {block}",
            )
            block_pns = {pn for _, pn, _ in block}
            self.assertEqual(
                len(block_pns), 1, f"output of concurrent jobs is interleaved: {block}"
            )
            seen.append(block[0][1])

        self.assertEqual(sorted(seen), sorted(pns))
        return seen

    def testParallelPkgPretend(self):
        """
        With --jobs greater than 1, pkg_pretend phases run concurrently, but
        their output is still emitted one package at a time (bug 579526).
        """
        pns = ("A", "B", "C", "D")
        ebuilds = {
            f"dev-libs/{pn}-1": {"EAPI": "8", "MISC_CONTENT": MISC_CONTENT}
            for pn in pns
        }

        playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
        try:
            emerge_cmd, env = self._playground_env(playground)
            returncode, output = self._run_emerge(
                emerge_cmd,
                env,
                ("--jobs=4",) + tuple(f"dev-libs/{pn}" for pn in pns),
            )
            if returncode != os.EX_OK:
                sys.stderr.write(output)
            self.assertEqual(os.EX_OK, returncode)

            markers = self._parse_markers(output)
            self._assert_not_interleaved(markers, pns)

            begins = [ts for kind, _, ts in markers if kind == "BEGIN"]
            ends = [ts for kind, _, ts in markers if kind == "END"]
            # If the phases ran concurrently then there is an instant at
            # which all of them were running.
            self.assertTrue(
                max(begins) < min(ends),
                f"pkg_pretend phases did not overlap: begins={begins} ends={ends}",
            )
        finally:
            playground.cleanup()

    def testSerialPkgPretend(self):
        """
        With a single job, pkg_pretend output is still complete and ordered.
        """
        pns = ("A", "B")
        ebuilds = {
            f"dev-libs/{pn}-1": {"EAPI": "8", "MISC_CONTENT": MISC_CONTENT}
            for pn in pns
        }

        playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
        try:
            emerge_cmd, env = self._playground_env(playground)
            returncode, output = self._run_emerge(
                emerge_cmd, env, tuple(f"dev-libs/{pn}" for pn in pns)
            )
            if returncode != os.EX_OK:
                sys.stderr.write(output)
            self.assertEqual(os.EX_OK, returncode)

            markers = self._parse_markers(output)
            self._assert_not_interleaved(markers, pns)

            # Serial phases cannot share their sleeps, so the whole run
            # takes at least one sleep per package.
            begins = [ts for kind, _, ts in markers if kind == "BEGIN"]
            ends = [ts for kind, _, ts in markers if kind == "END"]
            elapsed = max(ends) - min(begins)
            self.assertTrue(
                elapsed >= len(pns) * PRETEND_SLEEP,
                f"pkg_pretend phases were expected to be serial: "
                f"elapsed={elapsed} begins={begins} ends={ends}",
            )
        finally:
            playground.cleanup()

    def testInteractivePkgPretend(self):
        """
        A PROPERTIES=interactive package needs the terminal to itself, so
        the phases run serially and unbuffered even with --jobs greater
        than 1.
        """
        pns = ("A", "B")
        ebuilds = {
            f"dev-libs/{pn}-1": {"EAPI": "8", "MISC_CONTENT": MISC_CONTENT}
            for pn in pns
        }
        ebuilds["dev-libs/A-1"]["PROPERTIES"] = "interactive"

        playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
        try:
            emerge_cmd, env = self._playground_env(playground)
            returncode, output = self._run_emerge(
                emerge_cmd,
                env,
                ("--jobs=2",) + tuple(f"dev-libs/{pn}" for pn in pns),
            )
            if returncode != os.EX_OK:
                sys.stderr.write(output)
            self.assertEqual(os.EX_OK, returncode)

            markers = self._parse_markers(output)
            self._assert_not_interleaved(markers, pns)

            begins = [ts for kind, _, ts in markers if kind == "BEGIN"]
            ends = [ts for kind, _, ts in markers if kind == "END"]
            elapsed = max(ends) - min(begins)
            self.assertTrue(
                elapsed >= len(pns) * PRETEND_SLEEP,
                f"pkg_pretend phases were expected to be serial: "
                f"elapsed={elapsed} begins={begins} ends={ends}",
            )
        finally:
            playground.cleanup()

    def testParallelPkgPretendFailure(self):
        """
        A pkg_pretend failure aborts the merge, and its output is not lost
        when other jobs run concurrently.
        """
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8", "MISC_CONTENT": MISC_CONTENT},
            "dev-libs/B-1": {"EAPI": "8", "MISC_CONTENT": FAILING_MISC_CONTENT},
            "dev-libs/C-1": {"EAPI": "8", "MISC_CONTENT": MISC_CONTENT},
        }

        playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
        try:
            emerge_cmd, env = self._playground_env(playground)
            returncode, output = self._run_emerge(
                emerge_cmd,
                env,
                ("--jobs=3", "dev-libs/A", "dev-libs/B", "dev-libs/C"),
            )
            self.assertNotEqual(os.EX_OK, returncode)
            self.assertIn("PRETEND-FAIL B", output)
            # The packages which passed still ran, and nothing was merged.
            self.assertIn("PRETEND-END A", output)
            self.assertIn("PRETEND-END C", output)
            vardb = playground.trees[playground.eroot]["vartree"].dbapi
            self.assertEqual([], vardb.cpv_all())
        finally:
            playground.cleanup()
