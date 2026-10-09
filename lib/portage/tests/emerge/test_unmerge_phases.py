# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess

import portage
from portage.const import PORTAGE_PYM_PATH
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs

ECLASS = (
    "EXPORT_FUNCTIONS pkg_postrm",
    'marker_pkg_postrm() { echo "${MARKER}" > "${EROOT}/marker" || die; }',
)


class UnmergePhasesTestCase(TestCase):
    """
    A postrm that runs without a prerm before it must still see the
    package's saved environment.
    """

    def setUp(self):
        ebuilds = {
            "dev-libs/A-1": {
                "EAPI": "8",
                "MISC_CONTENT": 'inherit marker\n\nS="${WORKDIR}"\nMARKER=real',
            },
            "dev-libs/B-1": {"EAPI": "8", "MISC_CONTENT": 'S="${WORKDIR}"'},
        }
        self.playground = ResolverPlayground(
            ebuilds=ebuilds,
            eclasses={"marker": ECLASS},
            repo_configs={
                "test_repo": {"layout.conf": ("profile-formats = profile-bashrcs",)}
            },
        )
        settings = self.playground.settings
        self.eprefix = eprefix = settings["EPREFIX"]
        self.eroot = self.playground.eroot

        pythonpath = os.environ.get("PYTHONPATH")
        if pythonpath is not None and not pythonpath.strip():
            pythonpath = None
        if pythonpath is None or pythonpath.split(":")[0] != PORTAGE_PYM_PATH:
            pythonpath = PORTAGE_PYM_PATH + (":" + pythonpath if pythonpath else "")

        self.env = {
            "CLEAN_DELAY": "0",
            "PORTAGE_OVERRIDE_EPREFIX": eprefix,
            "FEATURES": "-sandbox -usersandbox",
            "PATH": settings.get("PATH"),
            "PORTAGE_INST_GID": str(os.getgid()),
            "PORTAGE_INST_UID": str(os.getuid()),
            "PORTAGE_PYTHON": portage._python_interpreter,
            "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", "1"),
            "PYTHONPATH": pythonpath,
        }

        self.tmpdir = os.path.join(eprefix, "var", "tmp", "portage")
        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
        for d in (self.playground.distdir, self.tmpdir, var_cache_edb):
            ensure_dirs(d)
        with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
            f.write(b"100")

    def tearDown(self):
        self.playground.cleanup()

    def emerge(self, *args):
        proc = subprocess.run(
            (
                portage._python_interpreter,
                "-b",
                "-Wd",
                os.path.join(str(self.bindir), "emerge"),
            )
            + args,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, os.EX_OK, proc.stdout)
        return proc.stdout

    def marker(self):
        with open(os.path.join(self.eroot, "marker")) as f:
            return f.read().strip()

    def test_postrm_without_prerm(self):
        self.emerge("--oneshot", "dev-libs/A")
        self.emerge("-C", "dev-libs/A")
        self.assertEqual(self.marker(), "real")

    def test_stale_environment_ignored(self):
        self.env["FEATURES"] += " keeptemp"
        self.emerge("--oneshot", "dev-libs/A")
        # keeptemp leaves ${T} behind after an unmerge, so a later unmerge
        # of the same PF can find an environment there. Plant one that would
        # win if postrm used it.
        temp = os.path.join(self.tmpdir, "._unmerge_", "dev-libs", "A-1", "temp")
        ensure_dirs(temp)
        with open(os.path.join(temp, "environment"), "w") as f:
            f.write('pkg_postrm() { echo stale > "${EROOT}/marker"; }\n')
        self.emerge("-C", "dev-libs/A")
        self.assertEqual(self.marker(), "real")

    def test_profile_bashrcs(self):
        # B defines neither phase, so only the profile's bashrc files can
        # make them run. Add them after the merge: functions they define
        # while B is built are saved in its environment.bz2.
        self.emerge("--oneshot", "dev-libs/B")
        profile = self.playground.settings.profiles[-1]
        with open(os.path.join(profile, "profile.bashrc"), "w") as f:
            f.write('post_pkg_postrm() { touch "${EROOT}/profile.bashrc"; }\n')
        with open(os.path.join(profile, "package.bashrc"), "w") as f:
            f.write("dev-libs/B b.bashrc\n")
        ensure_dirs(os.path.join(profile, "bashrc"))
        with open(os.path.join(profile, "bashrc", "b.bashrc"), "w") as f:
            f.write('post_pkg_prerm() { touch "${EROOT}/package.bashrc"; }\n')
        self.emerge("-C", "dev-libs/B")
        for name in ("profile.bashrc", "package.bashrc"):
            self.assertTrue(os.path.exists(os.path.join(self.eroot, name)), name)
