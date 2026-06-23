# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess
import sys

import portage
from portage.tests import TestCase, FunctionStep


class EmaintTestCase(TestCase):
    cmds = {}
    debug = False

    def __init__(self, *pargs, **kwargs):
        super().__init__(*pargs, **kwargs)

        for cmd in ("emaint",):
            for bindir in (self.bindir, self.sbindir):
                path = os.path.join(str(bindir), cmd)
                if os.path.exists(path):
                    self.cmds[cmd] = (portage._python_interpreter, "-b", "-Wd", path)
                    break
            else:
                raise AssertionError(
                    f"{cmd} binary not found in {self.bindir} or {self.sbindir}"
                )

    def runEmaintTest(self, steps, playground):
        settings = playground.settings
        eprefix = settings["EPREFIX"]
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

        try:
            if self.debug:
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

                if self.debug:
                    proc.wait()
                else:
                    output = proc.stdout.readlines()
                    proc.wait()
                    proc.stdout.close()
                    bad_returncode = proc.returncode != step.returncode
                    bad_output = step.output is not None and output not in output
                    if bad_returncode or bad_output:
                        for line in output:
                            sys.stderr.write(portage._unicode_decode(line))

                self.assertEqual(
                    step.returncode,
                    proc.returncode,
                    f"{step.command} (step {i}) failed with exit code {proc.returncode}",
                )

                if step.output is not None:
                    self.assertTrue(
                        isinstance(step.output, list) and len(step.output) > 0,
                        f"step {i} output token(s) not in a list",
                    )

                    for line in output:
                        if step.output[0] in line.decode():
                            del step.output[0]
                            if len(step.output) == 0:
                                break

                    self.assertTrue(
                        len(step.output) == 0,
                        f"{step.command} (step {i}) did not output {step.output}",
                    )

        finally:
            playground.cleanup()
