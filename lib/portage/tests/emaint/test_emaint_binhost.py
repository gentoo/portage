# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess
import sys
import time

import portage
from portage.tests import TestCase, CommandStep, FunctionStep
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class EmainBinhostTestCase(TestCase):
    def testCompressedIndex(self):
        debug = False

        user_config = {"make.conf": ('FEATURES="-compress-index"',)}

        binpkgs = {
            "app-misc/A-1": {
                "EAPI": "8",
                "DEPEND": "app-misc/B",
                "RDEPEND": "app-misc/C",
            },
        }

        playground = ResolverPlayground(
            binpkgs=binpkgs,
            user_config=user_config,
            debug=debug,
        )
        settings = playground.settings
        eprefix = settings["EPREFIX"]
        eroot = settings["EROOT"]
        bintree = playground.trees[eroot]["bintree"]

        cmds = {}
        for cmd in ("emaint",):
            for bindir in (self.bindir, self.sbindir):
                path = os.path.join(str(bindir), cmd)
                if os.path.exists(path):
                    cmds[cmd] = (portage._python_interpreter, "-b", "-Wd", path)
                    break
            else:
                raise AssertionError(
                    f"{cmd} binary not found in {self.bindir} or {self.sbindir}"
                )

        env = settings.environ()
        env.update(
            {
                "PORTAGE_OVERRIDE_EPREFIX": eprefix,
                "HOME": eprefix,
                "PYTHONDONTWRITEBYTECODE": os.environ.get(
                    "PYTHONDONTWRITEBYTECODE", ""
                ),
            }
        )

        def current_time(offset=0):
            t = time.time() + offset
            return (t, t)

        steps = (
            FunctionStep(
                function=lambda i: self.assertTrue(
                    os.path.exists(bintree._pkgindex_file), f"step {i}"
                ),
            ),
            # The compressed index should not exist yet because compress-index is disabled in make.conf.
            FunctionStep(
                function=lambda i: self.assertFalse(
                    os.path.exists(bintree._pkgindex_file + ".gz"), f"step {i}"
                )
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=cmds["emaint"] + ("binhost", "--fix"),
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=cmds["emaint"] + ("binhost", "--check"),
            ),
            FunctionStep(
                function=lambda i: self.assertTrue(
                    os.path.exists(bintree._pkgindex_file + ".gz"), f"step {i}"
                ),
            ),
            FunctionStep(
                function=lambda i: os.unlink(bintree._pkgindex_file + ".gz"),
            ),
            # It should report an error for a missing Packages.gz here.
            CommandStep(
                returncode=1,
                env={"FEATURES": "compress-index"},
                command=cmds["emaint"] + ("binhost", "--check"),
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=cmds["emaint"] + ("binhost", "--fix"),
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=cmds["emaint"] + ("binhost", "--check"),
            ),
            # Bump the timestamp of Packages so that Packages.gz becomes stale.
            FunctionStep(
                function=lambda i: os.utime(
                    bintree._pkgindex_file, current_time(offset=2)
                ),
            ),
            # It should report an error for stale Packages.gz here.
            CommandStep(
                returncode=1,
                env={"FEATURES": "compress-index"},
                command=cmds["emaint"] + ("binhost", "--check"),
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=cmds["emaint"] + ("binhost", "--fix"),
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=cmds["emaint"] + ("binhost", "--check"),
            ),
            # It should delete the unwanted Packages.gz here when compress-index is disabled.
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "-compress-index"},
                command=cmds["emaint"] + ("binhost", "--fix"),
            ),
            FunctionStep(
                function=lambda i: self.assertFalse(
                    os.path.exists(bintree._pkgindex_file + ".gz"), f"step {i}"
                )
            ),
        )

        try:
            if debug:
                # The subprocess inherits both stdout and stderr, for
                # debugging purposes.
                stdout = None
            else:
                # The subprocess inherits stderr so that any warnings
                # triggered by python -Wd will be visible.
                stdout = subprocess.PIPE

            for i, step in enumerate(steps):
                if isinstance(step, FunctionStep):
                    try:
                        step.function(i)
                    except Exception as e:
                        if isinstance(e, AssertionError) and f"step {i}" in str(e):
                            raise
                        raise AssertionError(
                            f"step {i} raised {e.__class__.__name__}"
                        ) from e
                    continue

                proc = subprocess.Popen(
                    step.command,
                    env=dict(env.items(), **(step.env or {})),
                    cwd=step.cwd,
                    stdout=stdout,
                )

                if debug:
                    proc.wait()
                else:
                    output = proc.stdout.readlines()
                    proc.wait()
                    proc.stdout.close()
                    if proc.returncode != step.returncode:
                        for line in output:
                            sys.stderr.write(portage._unicode_decode(line))

                self.assertEqual(
                    step.returncode,
                    proc.returncode,
                    f"{step.command} (step {i}) failed with exit code {proc.returncode}",
                )

        finally:
            playground.cleanup()
