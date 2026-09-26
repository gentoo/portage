# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import glob
import os
import re
import shutil
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

# Shell function shared by pkg_pretend and the fake fetch command. It waits
# until the number of jobs given in ${sync}/${kind} have started, or for the
# timeout given there, so that concurrent jobs are sure to overlap. While it
# waits it notes whether another job is running, which shows that serial jobs
# did not overlap; a serial run waits out the timeout once, in its first job.
# It prints 1 if it saw another job running and 0 otherwise.
WAIT_MARKERS = textwrap.dedent("""
    wait_markers() {
        local sync=$1 kind=$2 name=$3 count timeout i overlap=0
        local -a running started
        read -r count timeout < "${sync}/${kind}"
        : > "${sync}/${kind}-running-${name}"
        : > "${sync}/${kind}-started-${name}"
        for (( i = 0; i < timeout * 20; i++ )); do
            running=( "${sync}/${kind}"-running-* )
            started=( "${sync}/${kind}"-started-* )
            (( ${#running[@]} > 1 )) && overlap=1
            (( ${#started[@]} >= count )) && break
            sleep 0.05
        done
        rm "${sync}/${kind}-running-${name}"
        echo "${overlap}"
    }
    """)

# Each pkg_pretend prints when it started and finished, and waits on marker
# files in ${EPREFIX}/sync configured by _sync(). Without sync/pretend the
# phase does not wait.
MISC_CONTENT = WAIT_MARKERS + textwrap.dedent("""
    S="${WORKDIR}"

    pkg_pretend() {
        local sync=${EPREFIX}/sync overlap=0
        einfo "PRETEND-BEGIN ${PN} $(date +%s.%N)"
        einfo "PRETEND-BODY ${PN}"
        if [[ -f ${sync}/pretend ]]; then
            addwrite "${sync}"
            overlap=$(wait_markers "${sync}" pretend "${PN}")
        fi
        einfo "PRETEND-END ${PN} $(date +%s.%N) overlap=${overlap}"
    }
    """)

FAILING_MISC_CONTENT = textwrap.dedent("""
    S="${WORKDIR}"

    pkg_pretend() {
        eerror "PRETEND-FAIL ${PN}"
        die "pkg_pretend failed on purpose"
    }
    """)

MARKER_RE = re.compile(r"PRETEND-(BEGIN|BODY|END) (\w+)(?: (\d+\.\d+))?")
OVERLAP_RE = re.compile(r"PRETEND-END (\w+) \S+ overlap=([01])")

# How long a serial run waits for another phase to start. If the phases
# were not serial, the second one would start well within this time.
SERIAL_WINDOW = 2

# How long a phase waits for concurrent phases to start before giving up,
# so that a broken test fails instead of hanging.
BARRIER_TIMEOUT = 60

# FETCHCOMMAND for a fake:// binhost, which reports when each binary
# package download starts and finishes, and like pkg_pretend waits on
# marker files configured by _sync().
FAKE_FETCH_SCRIPT = "#!/usr/bin/env bash\n" + WAIT_MARKERS + textwrap.dedent("""
    src=${3#fake://}
    sync=${0%/*}/sync
    case ${src} in
    *.gpkg.tar)
        name=${src##*/}
        pn=${name%%-*}
        overlap=0
        echo "FETCH-BEGIN ${pn}"
        if [[ -f ${sync}/fetch ]]; then
            overlap=$(wait_markers "${sync}" fetch "${pn}")
        fi
        echo "FETCH-END ${pn} overlap=${overlap}"
        ;;
    esac
    exec cp "${src}" "$1/$2"
    """)

FETCH_MARKER_RE = re.compile(r"FETCH-(BEGIN|END) (\w+)")
FETCH_OVERLAP_RE = re.compile(r"FETCH-END \w+ overlap=1")


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

    def _sync(self, playground, pretend=None, fetch=None):
        """
        Reset the marker files in ${EPREFIX}/sync. Each of pretend and
        fetch is a (count, timeout) tuple: each pkg_pretend phase or fetch
        waits until count of them have started, or for timeout seconds.
        With None, the phases or fetches do not wait.
        """
        sync = os.path.join(playground.settings["EPREFIX"], "sync")
        shutil.rmtree(sync, ignore_errors=True)
        os.mkdir(sync)
        for name, config in (("pretend", pretend), ("fetch", fetch)):
            if config is not None:
                with open(os.path.join(sync, name), "w") as f:
                    f.write("{} {}\n".format(*config))

    def _assert_no_overlap(self, output, pns):
        """
        Assert that no pkg_pretend phase saw another one running.
        """
        overlaps = dict(OVERLAP_RE.findall(output))
        self.assertEqual(
            overlaps,
            {pn: "0" for pn in pns},
            "pkg_pretend phases were expected to be serial",
        )

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

    def _setup_binhost(self, pns):
        """
        Build the given packages and make them available only from a
        fake:// binhost. Return the playground, emerge command and
        environment.
        """
        ebuilds = {
            f"dev-libs/{pn}-1": {"EAPI": "8", "MISC_CONTENT": MISC_CONTENT}
            for pn in pns
        }
        playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
        self.addCleanup(playground.cleanup)
        emerge_cmd, env = self._playground_env(playground)
        eprefix = playground.settings["EPREFIX"]

        returncode, output = self._run_emerge(
            emerge_cmd,
            env,
            ("--buildpkgonly", "--jobs=2") + tuple(f"dev-libs/{pn}" for pn in pns),
        )
        if returncode != os.EX_OK:
            sys.stderr.write(output)
        self.assertEqual(os.EX_OK, returncode)

        binhost = os.path.join(eprefix, "binhost")
        os.rename(playground.pkgdir, binhost)
        fake_fetch = os.path.join(eprefix, "fake-fetch")
        with open(fake_fetch, "w") as f:
            f.write(FAKE_FETCH_SCRIPT)
        os.chmod(fake_fetch, 0o755)
        with open(os.path.join(eprefix, USER_CONFIG_PATH, "binrepos.conf"), "w") as f:
            f.write(textwrap.dedent(f"""\
                [test_binhost]
                sync-uri = fake://{binhost}
                verify-signature = false
                fetchcommand = {fake_fetch} "${{DISTDIR}}" "${{FILE}}" "${{URI}}"
                """))

        # Without parallel-fetch, each pkg_pretend job fetches its package.
        env["FEATURES"] = "-parallel-fetch"
        return playground, emerge_cmd, env

    def _assert_serial_fetches(self, text, pns):
        """
        Assert that each package was fetched once, and that no two
        fetches overlapped.
        """
        self.assertNotRegex(text, FETCH_OVERLAP_RE, "fetches overlap")
        markers = FETCH_MARKER_RE.findall(text)
        self.assertEqual(len(markers), 2 * len(pns), f"unexpected markers: {markers}")
        for i in range(0, len(markers), 2):
            (begin, pn), (end, end_pn) = markers[i : i + 2]
            self.assertEqual(
                (begin, end, pn),
                ("BEGIN", "END", end_pn),
                f"fetches overlap: {markers}",
            )
        self.assertEqual(sorted(pns), sorted(pn for _, pn in markers[::2]))

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
            self._sync(playground, pretend=(len(pns), BARRIER_TIMEOUT))
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
            self._sync(playground, pretend=(len(pns), SERIAL_WINDOW))
            returncode, output = self._run_emerge(
                emerge_cmd, env, tuple(f"dev-libs/{pn}" for pn in pns)
            )
            if returncode != os.EX_OK:
                sys.stderr.write(output)
            self.assertEqual(os.EX_OK, returncode)

            markers = self._parse_markers(output)
            self._assert_not_interleaved(markers, pns)

            self._assert_no_overlap(output, pns)
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
            self._sync(playground, pretend=(len(pns), SERIAL_WINDOW))
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
            self._assert_no_overlap(output, pns)
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
            self._sync(playground, pretend=(2, BARRIER_TIMEOUT))
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

    def testParallelPkgPretendBinpkgFetch(self):
        """
        Binary packages fetched by concurrent pkg_pretend jobs are fetched
        one at a time, with output in the fetch log.
        """
        pns = ("A", "B")
        playground, emerge_cmd, env = self._setup_binhost(pns)
        eprefix = playground.settings["EPREFIX"]
        args = ("--getbinpkgonly", "--jobs=2") + tuple(f"dev-libs/{pn}" for pn in pns)
        pkgdir = os.path.join(eprefix, "var", "cache", "binhost")
        fetch_log = os.path.join(eprefix, "var", "log", "emerge-fetch.log")

        # With parallel-fetch, a job whose prefetcher has not started yet
        # fetches its package while another prefetcher is running.
        for features in ("-parallel-fetch", "parallel-fetch"):
            with self.subTest(features=features):
                shutil.rmtree(pkgdir, ignore_errors=True)
                self._sync(playground, fetch=(len(pns), SERIAL_WINDOW))
                if os.path.exists(fetch_log):
                    os.unlink(fetch_log)
                env["FEATURES"] = features
                returncode, output = self._run_emerge(emerge_cmd, env, args)
                if returncode != os.EX_OK:
                    sys.stderr.write(output)
                self.assertEqual(os.EX_OK, returncode)
                self.assertNotRegex(output, FETCH_MARKER_RE)
                with open(fetch_log, encoding="utf-8") as f:
                    self._assert_serial_fetches(f.read(), pns)
                self._assert_not_interleaved(self._parse_markers(output), pns)

                # The fetch notices are shown before the pkg_pretend output
                # that waits on them, and the fetch log is named once.
                first_pretend = output.index("PRETEND-BEGIN")
                for pn in pns:
                    notice = re.search(
                        rf"Fetching in the background: \S*/{pn}-1-1\.gpkg\.tar",
                        output,
                    )
                    self.assertIsNotNone(notice, f"no fetch notice for {pn}")
                    self.assertLess(notice.start(), first_pretend)
                self.assertEqual(1, output.count("tail -f "))

        # Root can write to a read-only fetch log.
        if os.getuid() == 0:
            return
        # Without a writable fetch log, fetch output goes to the terminal.
        # Prefetchers write to the fetch log regardless, so disable them.
        shutil.rmtree(pkgdir)
        self._sync(playground, fetch=(len(pns), SERIAL_WINDOW))
        os.chmod(fetch_log, 0o444)
        env["FEATURES"] = "-parallel-fetch"
        returncode, output = self._run_emerge(emerge_cmd, env, args)
        if returncode != os.EX_OK:
            sys.stderr.write(output)
        self.assertEqual(os.EX_OK, returncode)
        self._assert_serial_fetches(output, pns)

    def testParallelPkgPretendBinpkgFetchFailure(self):
        """
        A failed fetch whose output is in the fetch log is reported on the
        terminal.
        """
        pns = ("A", "B")
        playground, emerge_cmd, env = self._setup_binhost(pns)
        eprefix = playground.settings["EPREFIX"]
        (binpkg,) = glob.glob(
            os.path.join(eprefix, "binhost", "**", "B-1-1.gpkg.tar"),
            recursive=True,
        )
        os.unlink(binpkg)
        self._sync(playground, fetch=(len(pns), SERIAL_WINDOW))

        returncode, output = self._run_emerge(
            emerge_cmd,
            env,
            ("--getbinpkgonly", "--jobs=2", "dev-libs/A", "dev-libs/B"),
        )
        self.assertNotEqual(os.EX_OK, returncode, output)
        self.assertIn("PRETEND-END A", output)
        self.assertIn("Fetch of dev-libs/B-1 failed, see ", output)
