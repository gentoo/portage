# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
from unittest import mock

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess
from _emerge.EbuildPhase import EbuildPhase
from _emerge.Package import Package
from portage import _python_interpreter
from portage.package.ebuild.config import config
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util._async.SchedulerInterface import SchedulerInterface
from portage.util._eventloop.global_event_loop import global_event_loop


class ExitTimeoutWarningTestCase(TestCase):
    """
    Check that a phase which leaves a background process holding its
    output open is reported when _exit_timeout fires.
    """

    def testExitTimeoutWarning(self):
        cpv = "dev-libs/A-1"
        playground = ResolverPlayground(ebuilds={cpv: {"EAPI": "8"}})
        try:
            root_config = playground.trees[playground.eroot]["root_config"]
            portdb = root_config.trees["porttree"].dbapi
            settings = config(clone=playground.settings)
            metadata = dict(
                zip(Package.metadata_keys, portdb.aux_get(cpv, Package.metadata_keys))
            )
            pkg = Package(
                built=False,
                cpv=cpv,
                installed=False,
                metadata=metadata,
                root_config=root_config,
                type_name="ebuild",
            )
            settings.setcpv(pkg)
            settings["EBUILD"] = portdb.findname(cpv)
            settings["PORTAGE_PYTHON"] = _python_interpreter
            settings["PORTAGE_BUILDDIR"] = os.path.join(settings["PORTAGE_TMPDIR"], cpv)
            settings["HOME"] = os.path.join(settings["PORTAGE_BUILDDIR"], "homedir")
            settings["T"] = os.path.join(settings["PORTAGE_BUILDDIR"], "temp")
            for x in ("PORTAGE_BUILDDIR", "HOME", "T"):
                os.makedirs(settings[x])
            os.makedirs(os.path.join(settings["PORTAGE_BUILDDIR"], ".ipc"))
            # The phase output has to go through a log pipe, since that
            # is what the background process holds open.
            settings["PORTAGE_LOG_FILE"] = os.path.join(settings["T"], "build.log")
            # Pretend the ebuild has been sourced already, with a phase
            # that leaves a process holding its output open.
            with open(os.path.join(settings["T"], "environment"), "w") as f:
                f.write("pkg_pretend() { sleep 5 & }\n")

            scheduler = SchedulerInterface(global_event_loop())
            ebuild_phase = EbuildPhase(
                background=False,
                phase="pretend",
                scheduler=scheduler,
                settings=settings,
            )
            with mock.patch.object(AbstractEbuildProcess, "_exit_timeout", 1):
                ebuild_phase.start()
                ebuild_phase.wait()

            # The phase reported success before it was killed.
            self.assertEqual(ebuild_phase.returncode, os.EX_OK)
            with open(settings["PORTAGE_LOG_FILE"]) as f:
                log = f.read()
            self.assertIn("appears to have left", log)
        finally:
            playground.cleanup()
