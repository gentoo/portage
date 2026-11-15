# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import itertools
import os
import tempfile
import shutil
import subprocess
import sys
import portage

from portage.const import (
    PORTAGE_PYM_PATH,
    USER_CONFIG_PATH,
)
from portage.const import USER_CONFIG_PATH
from portage.dep import Atom
from portage.package.ebuild.doebuild import _phase_func_map
from portage.util import ensure_dirs
from portage.package.ebuild._config.LicenseManager import LicenseManager
from portage.package.ebuild.config import config
from portage.tests import CommandStep, FunctionStep, TestCase
from portage.tests.ebuild.MockUserPatches import MockUserPatches
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)
from portage.util import normalize_path
from portage.versions import _pkg_str


def _get_hook_names():
    hooks = {}
    for prefix, phase in itertools.product(("pre_", "post_"), _phase_func_map.values()):
        if phase in (
            # pkg_config, pkg_info, pkg_nofetch are only run when explicitly requested
            "pkg_config",
            "pkg_info",
            "pkg_nofetch",
            # pkg_prerm, pkg_postrm only apply when we have an existing install
            "pkg_prerm",
            "pkg_postrm",
            # pkg_pretend has its own T
            "pkg_pretend",
        ):
            continue

        comb = f"{prefix}{phase}"
        hooks[comb] = f"{prefix}{phase}"
    return hooks


def _get_stub_phase_definitions():
    """
    Provide stub definitions of all phases so they're not skipped and
    we can execute hooks for them.
    """
    defs = {}
    for phase in _phase_func_map.values():
        content = ":;"
        # We can't always call 'default' because pkg_pretend used to have
        # one but it was removed in later EAPIs
        if phase in ("src_prepare", "src_install"):
            content = "default ;"
        defs[phase] = f"""{phase}() {{ {content} }}"""
    return defs


def _get_hooked_phase_definitions():
    """
    Provide a set of hook definitions which write a cookie to the best
    location depending on the phase such that it persists for later
    retrieval.

    The final destination of the cookie is ${EPREFIX}/usr/share/doc/${PF}/phase
    with a list of all executed phase hooks.
    """
    hooks = []
    for phase in _get_hook_names().values():
        hooks.append(f"""
            {phase}() {{
                case "${{EBUILD_PHASE_FUNC}}" in
                    pkg_preinst)
                        # We're about to write to the live filesystem, so
                        # stash it into the prepared image.
                        X="${{ED}}"/usr/share/doc/${{PF}}
                        ;;
                    pkg_postinst)
                        # We've already merged it, so can't use T or ED.
                        X="${{EPREFIX}}"/usr/share/doc/${{PF}}
                        ;;
                    *)
                        X="${{T}}"
                        ;;
                esac

                # DOCS has already done its job by this point, so stash it in
                # to the image instead.
                [[ "{phase}" == "post_src_install" ]] && X="${{ED}}"/usr/share/doc/${{PF}}

                echo {phase} >> "${{X}}"/phase || die
            }}
        """)
    return hooks


HOOKS = _get_hooked_phase_definitions()


class ProfileExtensionTestCase(TestCase):

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
            "PORTAGE_COMPRESS": "",
            "FEATURES": "test",
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

    def testPackageBashrc(self):
        # Indirection for newline is needed for Python 3.9.
        newline = "\n"
        ebuilds = {
            "dev-libs/A-1": {
                "EAPI": "8",
                "MISC_CONTENT": f"""
                    S="${{WORKDIR}}"
                    DOCS=( "${{T}}"/phase )
                    {newline.join(_get_stub_phase_definitions().values())}
                """,
            },
            "dev-libs/B-1": {},
        }

        repo_configs = {
            "test_repo": {
                "layout.conf": ("profile-formats = profile-bashrcs",),
                "package.bashrc": ("dev-libs/A test.conf",),
            }
        }

        profiles = (
            (
                "default/linux",
                {
                    "eapi": ("5",),
                    "packages": (
                        "*sys-libs/A",
                        "app-misc/A",
                        "app-misc/B",
                        "app-misc/C",
                    ),
                    "package.bashrc": ("dev-libs/A test.conf",),
                },
            ),
            (
                "default/linux/x86",
                {
                    "eapi": ("5",),
                    "packages": ("-app-misc/B",),
                    "parent": ("..",),
                    "package.bashrc": ("dev-libs/A test.conf",),
                    "bashrc/test.conf": ("\n".join(HOOKS),),
                },
            ),
        )

        user_config = {
            "package.mask": ("dev-libs/E",),
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--autounmask": "n"},
                success=True,
                mergelist=["dev-libs/A-1"],
            ),
        )

        debug = True
        playground = ResolverPlayground(
            debug=debug, ebuilds=ebuilds, repo_configs=repo_configs
        )
        emerge_cmd, env = self._playground_env(playground)
        eprefix = env["PORTAGE_OVERRIDE_EPREFIX"]

        # TODO: test non-fresh install, other issues matt raised in PR
        # TODO: test package.bashrc separately from /etc/portage/bashrc
        # TODO: test profile.bashrc
        test_commands = (
            CommandStep(
                returncode=os.EX_OK,
                env=env,
                command=emerge_cmd
                + (
                    "--oneshot",
                    "dev-libs/A",
                ),
            ),
            # Compare the list of defined hooks with the hooks actually
            # executed. This is for a fresh install of the package.
            FunctionStep(
                function=lambda i: self.assertEqual(
                    sorted(_get_hook_names()),
                    sorted(
                        (
                            x.strip()
                            for x in portage.util.grablines(
                                os.path.join(
                                    eprefix, "usr", "share", "doc", "A-1", "phase"
                                )
                            )
                        )
                    ),
                    f"step {i}",
                )
            ),
        )

        try:
            repo_dir = playground.settings.repositories.get_location_for_name(
                "test_repo"
            )
            profile_root = os.path.join(repo_dir, "profiles")

            for p, data in profiles:
                prof_path = os.path.join(profile_root, p)
                ensure_dirs(prof_path)
                for k, v in data.items():
                    file_name = os.path.join(prof_path, k)
                    if "/" in k and not os.path.isdir(os.path.dirname(file_name)):
                        os.makedirs(os.path.dirname(file_name))

                    with open(
                        os.path.join(prof_path, k),
                        mode="w",
                        encoding="utf-8",
                    ) as f:
                        f.writelines(f"{line}\n" for line in v)

            # The config must be reloaded in order to account
            # for the above profile customizations.
            playground.reload_config()

            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)

            for i, step in enumerate(test_commands):
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

                if debug:
                    # The subprocess inherits both stdout and stderr, for
                    # debugging purposes.
                    stdout = None
                else:
                    # The subprocess inherits stderr so that any warnings
                    # triggered by python -Wd will be visible.
                    stdout = subprocess.PIPE

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
                            sys.stderr.write(line.decode("utf-8", "replace"))

                self.assertEqual(
                    step.returncode,
                    proc.returncode,
                    f"{step.command} (step {i}) failed with exit code {proc.returncode}",
                )

                # returncode, output = self._run_emerge(emerge_cmd, emerge_env, ("dev-libs/A",))
                # if returncode != os.EX_OK:
                #    sys.stderr.write(output)
                # self.assertEqual(os.EX_OK, returncode)
        finally:
            pass
            # playground.cleanup()
