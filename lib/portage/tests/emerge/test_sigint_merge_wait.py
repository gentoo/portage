# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import signal
import subprocess
import textwrap
import time

import portage
from portage.const import PORTAGE_PYM_PATH
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs

POLL_TIMEOUT = 60
POLL_INTERVAL = 0.1


def misc_content(pn):
    """src_compile that announces itself, then waits to be released."""
    return textwrap.dedent(f"""
        S="${{WORKDIR}}"

        src_compile() {{
            local dir=${{PORTAGE_TMPDIR}}/portage
            local i
            > "${{dir}}/{pn}-building" || die "failed to announce {pn}"
            for ((i = 0; i < {int(POLL_TIMEOUT / POLL_INTERVAL)}; i++)); do
                [[ -e ${{dir}}/{pn}-release ]] && return
                sleep {POLL_INTERVAL}
            done
            die "timed out waiting for {pn}-release"
        }}
        """)


def read_log(log_path):
    with open(log_path, encoding="utf-8", errors="replace") as f:
        return f.read()


class SigintMergeWaitTestCase(TestCase):
    def _wait_for(self, condition, proc, log_path, what):
        deadline = time.time() + POLL_TIMEOUT
        while not condition():
            if proc.poll() is not None:
                self.fail(f"emerge exited before {what}:\n{read_log(log_path)}")
            if time.time() > deadline:
                self.fail(f"timed out waiting for {what}:\n{read_log(log_path)}")
            time.sleep(POLL_INTERVAL)

    def testSigintDoesNotDrainMergeWaitQueue(self):
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8", "MISC_CONTENT": misc_content("A")},
            "dev-libs/B-1": {"EAPI": "8", "MISC_CONTENT": misc_content("B")},
        }

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            settings = playground.settings
            eprefix = settings["EPREFIX"]
            portage_tmpdir = os.path.join(eprefix, "var", "tmp")

            portage_python = portage._python_interpreter
            emerge_cmd = (
                portage_python,
                "-b",
                "-Wd",
                os.path.join(str(self.bindir), "emerge"),
            )

            pythonpath = os.environ.get("PYTHONPATH")
            if pythonpath is not None and not pythonpath.strip():
                pythonpath = None
            if pythonpath is None or pythonpath.split(":")[0] != PORTAGE_PYM_PATH:
                pythonpath = PORTAGE_PYM_PATH + (":" + pythonpath if pythonpath else "")

            env = {
                "PORTAGE_OVERRIDE_EPREFIX": eprefix,
                "FEATURES": "parallel-install merge-wait",
                "PATH": settings.get("PATH"),
                "PORTAGE_INST_GID": str(os.getgid()),
                "PORTAGE_INST_UID": str(os.getuid()),
                "PORTAGE_PYTHON": portage_python,
                "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
                "PYTHONDONTWRITEBYTECODE": os.environ.get(
                    "PYTHONDONTWRITEBYTECODE", "1"
                ),
                "PYTHONPATH": pythonpath,
            }

            handshake_dir = os.path.join(portage_tmpdir, "portage")
            var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
            for d in (playground.distdir, handshake_dir, var_cache_edb):
                ensure_dirs(d)
            with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
                f.write(b"100")

            def handshake(name):
                return os.path.join(handshake_dir, name)

            def release(name):
                with open(handshake(f"{name}-release"), "wb"):
                    pass

            log_path = os.path.join(portage_tmpdir, "emerge-sigint.log")
            with open(log_path, "wb") as log_file:
                proc = subprocess.Popen(
                    emerge_cmd
                    + (
                        "--jobs=2",
                        "--jobs-tmpdir-require-free-gb=0",
                        "dev-libs/A",
                        "dev-libs/B",
                    ),
                    env=env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                )

                def a_is_queued():
                    # Scheduler._build_exit() appends the merge to
                    # _merge_wait_queue before it drops the job count, so
                    # a return to one running job after both were running
                    # means A is queued.
                    _, both_running, tail = read_log(log_path).partition("2 running")
                    return bool(both_running) and "1 running" in tail

                try:
                    self._wait_for(
                        lambda: os.path.exists(handshake("A-building"))
                        and os.path.exists(handshake("B-building")),
                        proc,
                        log_path,
                        "both builds to start",
                    )
                    release("A")
                    self._wait_for(
                        a_is_queued,
                        proc,
                        log_path,
                        "dev-libs/A-1 to reach the merge-wait queue",
                    )

                    os.kill(proc.pid, signal.SIGINT)
                    # os.kill() signals only emerge, not B as ^C would, so
                    # release B or emerge waits out B's timeout.
                    release("B")

                    try:
                        returncode = proc.wait(timeout=POLL_TIMEOUT)
                    except subprocess.TimeoutExpired:
                        self.fail(
                            f"emerge did not exit after SIGINT:\n{read_log(log_path)}"
                        )
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()

            log = read_log(log_path)
            self.assertEqual(
                returncode,
                128 + signal.SIGINT,
                f"unexpected returncode {returncode}:\n{log}",
            )
            self.assertNotIn(
                "Installing (",
                log,
                "a merge was started after SIGINT was sent",
            )
        finally:
            playground.cleanup()
