# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import re
import stat
import subprocess

import portage
from portage.const import PORTAGE_PYM_PATH
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs

ECLASS = (
    "EXPORT_FUNCTIONS src_install pkg_prerm pkg_postrm",
    "order_src_install() {",
    '    dodir "/usr/share/${P}"',
    '    touch "${ED}/usr/share/${P}/file" || die',
    "}",
    "order_pkg_prerm() {",
    "    local state=gone",
    "    [[ -n ${DEPENDENT} ]] &&",
    "        [[ -e ${EROOT}/usr/share/${DEPENDENT}/file ||",
    "            ! -e ${EROOT}/postrm-${DEPENDENT} ]] &&",
    "        state=present",
    '    echo "${PN} ${state}" >> "${EROOT}/order.log" || die',
    "    if [[ -n ${PARTNER} ]]; then",
    '        touch "${EROOT}/started-${PN}" || die',
    "        local i",
    "        for (( i = 0; i < 300; i++ )); do",
    "            [[ -e ${EROOT}/started-${PARTNER} ]] && break",
    "            sleep 0.1",
    "        done",
    "        [[ -e ${EROOT}/started-${PARTNER} ]] && state=concurrent || state=alone",
    '        echo "${PN} ${state}" >> "${EROOT}/order.log" || die',
    "    fi",
    "}",
    "order_pkg_postrm() {",
    '    touch "${EROOT}/postrm-${P}" || die',
    "}",
)


class DepcleanParallelTestCase(TestCase):
    """
    With --jobs, depclean unmerges packages in parallel, but a package is
    unmerged only after the packages that depend on it.
    """

    def setUp(self):
        def ebuild(rdepend="", slot="0", install=None, **variables):
            misc = ["inherit order", 'S="${WORKDIR}"']
            misc += [f"{k}={v}" for k, v in variables.items()]
            if install is not None:
                misc.append(f"src_install() {{ order_src_install; {install}; }}")
            return {
                "EAPI": "8",
                "SLOT": slot,
                "RDEPEND": rdepend,
                "MISC_CONTENT": "\n".join(misc),
            }

        ebuilds = {
            "dev-libs/A-1": ebuild("dev-libs/B"),
            "dev-libs/B-1": ebuild("dev-libs/C", DEPENDENT="A-1"),
            "dev-libs/C-1": ebuild(DEPENDENT="B-1"),
            "dev-libs/D-1": ebuild(PARTNER="E"),
            "dev-libs/E-1": ebuild(PARTNER="D"),
            "dev-libs/F-1": ebuild(slot="1", PARTNER="G"),
            "dev-libs/F-2": ebuild(slot="2"),
            "dev-libs/G-1": ebuild(slot="1", PARTNER="F"),
            "dev-libs/G-2": ebuild(slot="2"),
            "dev-libs/L-1": ebuild(
                DEPENDENT="M-1",
                install="dosym real /usr/share/link",
            ),
            "dev-libs/M-1": ebuild(
                install="insinto /usr/share/link; newins - m < /dev/null"
            ),
            "dev-libs/W-1": {"EAPI": "8", "MISC_CONTENT": 'S="${WORKDIR}"'},
        }
        self.playground = ResolverPlayground(
            ebuilds=ebuilds, eclasses={"order": ECLASS}
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
            # Without ebuild-locks, prerm phases may run concurrently.
            "FEATURES": "-sandbox -usersandbox -ebuild-locks",
            "PATH": settings.get("PATH"),
            "PORTAGE_INST_GID": str(os.getgid()),
            "PORTAGE_INST_UID": str(os.getuid()),
            "PORTAGE_PYTHON": portage._python_interpreter,
            "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", "1"),
            "PYTHONPATH": pythonpath,
        }

        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
        for d in (
            self.playground.distdir,
            os.path.join(eprefix, "var", "tmp", "portage"),
            var_cache_edb,
        ):
            ensure_dirs(d)
        with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
            f.write(b"100")

    def tearDown(self):
        self.playground.cleanup()

    def emerge(self, *args, returncode=os.EX_OK):
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
        self.assertEqual(proc.returncode, returncode, proc.stdout)
        return proc.stdout

    def installed(self):
        return sorted(self.playground.trees[self.eroot]["vartree"].dbapi.cpv_all())

    def order_log(self):
        with open(os.path.join(self.eroot, "order.log")) as f:
            return set(f.read().splitlines())

    def test_depclean_parallel(self):
        self.emerge("--oneshot", "dev-libs/A", "dev-libs/D", "dev-libs/E")
        # depclean refuses to run with an empty @world.
        self.emerge("dev-libs/W")
        output = self.emerge("--depclean", "--jobs=4")

        self.assertEqual(self.installed(), ["dev-libs/W-1"], output)
        for pn in "ABCDE":
            path = os.path.join(self.eroot, "usr", "share", f"{pn}-1")
            self.assertFalse(os.path.exists(path), path)

        self.assertEqual(
            self.order_log(),
            {
                "A gone",
                "B gone",
                "C gone",
                "D gone",
                "E gone",
                "D concurrent",
                "E concurrent",
            },
            output,
        )

    def test_depclean_parallel_failure(self):
        self.emerge("--oneshot", "dev-libs/A")
        self.emerge("dev-libs/W")
        # A suid file with a hardlink that B does not own makes the
        # unmerge of B fail.
        path = os.path.join(self.eroot, "usr", "share", "B-1", "file")
        os.chmod(path, os.stat(path).st_mode | stat.S_ISUID)
        os.link(path, os.path.join(self.eroot, "hardlink"))
        output = self.emerge("--depclean", "--jobs=4", returncode=1)

        self.assertIn("!!! unmerge FAILURE: dev-libs/B-1", output)
        log_path = re.search(r"^!!! Log file: '(.*)'$", output, re.M).group(1)
        with open(log_path) as f:
            self.assertIn("suspicious hardlink", f.read())
        self.assertIn("!!! Not unmerged: dev-libs/C-1", output)
        self.assertEqual(
            self.installed(), ["dev-libs/B-1", "dev-libs/C-1", "dev-libs/W-1"], output
        )
        self.assertEqual(self.order_log(), {"A gone"}, output)

    def test_prune_parallel(self):
        # Without --nodeps, --prune is a depclean. With it, as with
        # --clean, the packages are unmerged in no particular order.
        self.emerge("dev-libs/F:1", "dev-libs/F:2", "dev-libs/G:1", "dev-libs/G:2")
        output = self.emerge(
            "--prune", "--nodeps", "--jobs=4", "dev-libs/F", "dev-libs/G"
        )

        self.assertEqual(self.installed(), ["dev-libs/F-2", "dev-libs/G-2"], output)
        self.assertEqual(
            self.order_log(),
            {"F gone", "G gone", "F concurrent", "G concurrent"},
            output,
        )

    def test_depclean_parallel_symlink(self):
        # M installs a file through L's symlink to a directory, so L is
        # unmerged after M, which lets it remove the symlink.
        self.emerge("--oneshot", "dev-libs/L")
        self.emerge("--oneshot", "dev-libs/M")
        self.emerge("dev-libs/W")
        output = self.emerge("--depclean", "--jobs=4")

        self.assertEqual(self.installed(), ["dev-libs/W-1"], output)
        link = os.path.join(self.eroot, "usr", "share", "link")
        self.assertFalse(os.path.lexists(link), output)
        self.assertEqual(self.order_log(), {"L gone", "M gone"}, output)
