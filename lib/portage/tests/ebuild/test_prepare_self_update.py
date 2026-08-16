# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import shutil
import subprocess
import tempfile

import portage
from portage.const import PORTAGE_BIN_PATH, PORTAGE_PYM_PATH
from portage.tests import TestCase

# Runs in a subprocess with an installed copy of portage which is
# deleted after _prepare_self_update() has run, in order to emulate a
# self update which installs to a different location, as happens when
# PYTHON_TARGETS changes (bug 976616).
_SCRIPT = """
import multiprocessing
import os
import shutil
import sys

def child():
    import portage.dbapi.vartree


if __name__ == "__main__":
    sys.path.insert(0, sys.argv[1])

    import portage
    from portage.package.ebuild.doebuild import _prepare_self_update

    # The modules imported below must not be imported before the update.
    assert "portage.util.env_update" not in sys.modules
    assert "portage.dbapi.vartree" not in sys.modules

    _prepare_self_update({"PORTAGE_TMPDIR": sys.argv[2]})

    shutil.rmtree(os.path.dirname(sys.argv[1]))

    import portage.util.env_update

    ctx = multiprocessing.get_context(sys.argv[3])
    proc = ctx.Process(target=child)
    proc.start()
    proc.join()
    sys.exit(proc.exitcode)
"""


class PrepareSelfUpdateTestCase(TestCase):
    def testPrepareSelfUpdate(self):
        tmpdir = tempfile.mkdtemp()
        try:
            script = os.path.join(tmpdir, "self_update.py")
            with open(script, "w") as f:
                f.write(_SCRIPT)

            # PYTHONPATH would provide a second copy of the modules
            # which are expected to become unimportable.
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)

            for start_method in ("fork", "forkserver"):
                # The installed copy is deleted by the subprocess, so
                # create a fresh one for each start method.
                base_path = os.path.join(tmpdir, f"base-{start_method}")
                pym_path = os.path.join(base_path, os.path.basename(PORTAGE_PYM_PATH))
                os.mkdir(base_path)
                shutil.copytree(PORTAGE_PYM_PATH, pym_path, symlinks=True)
                shutil.copytree(
                    PORTAGE_BIN_PATH,
                    os.path.join(base_path, os.path.basename(PORTAGE_BIN_PATH)),
                    symlinks=True,
                )

                proc = subprocess.run(
                    [
                        portage._python_interpreter,
                        script,
                        pym_path,
                        tmpdir,
                        start_method,
                    ],
                    env=env,
                    stderr=subprocess.PIPE,
                )
                self.assertEqual(
                    proc.returncode,
                    os.EX_OK,
                    msg=proc.stderr.decode(errors="replace"),
                )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
