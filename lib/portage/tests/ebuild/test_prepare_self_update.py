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


# Runs in a subprocess with an installed copy of portage which is
# overwritten with incompatible modules after _prepare_self_update() has
# run, in order to emulate a self update which installs to the same
# location. Modules imported after the update must come from the backup
# copy of the running version, since mixing them with the modules which
# are already imported can call a function with a signature it no longer
# has.
_SKEW_SCRIPT = """
import multiprocessing
import os
import sys

POISON = "_SELF_UPDATE_POISON = True"


def check():
    import portage.util.movefile
    import portage.dbapi.vartree

    for mod in (portage.util.movefile, portage.dbapi.vartree):
        assert not hasattr(mod, "_SELF_UPDATE_POISON"), mod.__file__
        assert mod.__file__.startswith(portage._pym_path + os.sep), mod.__file__

    # vartree calls into movefile, so the two must agree.
    assert portage.dbapi.vartree.movefile is portage.util.movefile.movefile


def child():
    check()


if __name__ == "__main__":
    sys.path.insert(0, sys.argv[1])

    import portage
    from portage.package.ebuild.doebuild import _prepare_self_update

    # The modules imported by check() must not be imported before the update.
    assert "portage.util.movefile" not in sys.modules
    assert "portage.dbapi.vartree" not in sys.modules

    _prepare_self_update({"PORTAGE_TMPDIR": sys.argv[2]})

    for relative_path in ("portage/util/movefile.py", "portage/dbapi/vartree.py"):
        with open(os.path.join(sys.argv[1], relative_path), "w") as f:
            f.write(POISON)

    check()

    ctx = multiprocessing.get_context(sys.argv[3])
    proc = ctx.Process(target=child)
    proc.start()
    proc.join()
    sys.exit(proc.exitcode)
"""


class PrepareSelfUpdateTestCase(TestCase):
    def _run(self, script_text):
        tmpdir = tempfile.mkdtemp()
        try:
            script = os.path.join(tmpdir, "self_update.py")
            with open(script, "w") as f:
                f.write(script_text)

            # PYTHONPATH would provide a second copy of the modules
            # which are expected to become unimportable.
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)

            for start_method in ("fork", "forkserver"):
                # The installed copy is modified by the subprocess, so
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

    def testPrepareSelfUpdate(self):
        self._run(_SCRIPT)

    def testPrepareSelfUpdateVersionSkew(self):
        self._run(_SKEW_SCRIPT)
