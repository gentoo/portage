# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import pytest

from portage.tests import CommandStep, FunctionStep
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.tests.emaint.EmaintTestCase import EmaintTestCase


class EmaintWorldTestCase(EmaintTestCase):
    def in_world(self, playground, atom):
        world_file = os.path.join(playground.eroot, "var", "lib", "portage", "world")
        with open(world_file) as f:
            atoms = (line.strip() for line in f.readlines())
            return atom in atoms

    def testWorldInstalled(self):
        ebuilds = {
            "app-misc/A-1.0": {},
            "app-misc/B-1.0": {},
        }

        installed = {
            "app-misc/A-1.0": {},
        }

        world = (
            "app-misc/A",
            "app-misc/B",
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=installed,
            world=world,
        )

        emaint = self.cmds["emaint"]
        steps = (
            CommandStep(
                returncode=1,
                command=emaint + ("world", "--check"),
                output=["'app-misc/B' is not installed"],
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("world", "--fix"),
            ),
            FunctionStep(
                function=lambda i: self.assertTrue(
                    self.in_world(playground, "app-misc/A"), f"step {i}"
                )
            ),
            FunctionStep(
                function=lambda i: self.assertFalse(
                    self.in_world(playground, "app-misc/B"), f"step {i}"
                )
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("world", "--check"),
            ),
        )

        self.runEmaintTest(steps, playground)

    def testWorldMasked(self):
        ebuilds = {
            "app-misc/A-1.0": {},
            "app-misc/B-1.0": {"KEYWORDS": "x86~"},
            # same masking reason - to be reported only once for all ebuilds
            "app-misc/C-1.0": {"LICENSE": "TEST"},
            "app-misc/C-2.0": {"LICENSE": "TEST"},
            # live ebuild - to be omitted from reported masking reasons
            "app-misc/C-9999": {"KEYWORDS": "", "PROPERTIES": "live"},
        }

        user_config = {
            "package.mask": (">=app-misc/C-2.0",),
        }

        world = (
            "app-misc/A",
            "app-misc/B",
            "app-misc/C",
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=ebuilds,
            user_config=user_config,
            world=world,
        )

        emaint = self.cmds["emaint"]
        steps = (
            CommandStep(
                returncode=1,
                command=emaint + ("world", "--check"),
                output=[
                    "'app-misc/B' has no visible ebuilds [missing keyword]",
                    "'app-misc/C' has no visible ebuilds [TEST license(s), package.mask]",
                ],
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("world", "--fix"),
            ),
            FunctionStep(
                function=lambda i: self.assertTrue(
                    self.in_world(playground, "app-misc/A"), f"step {i}"
                ),
            ),
            FunctionStep(
                function=lambda i: self.assertFalse(
                    self.in_world(playground, "app-misc/B"), f"step {i}"
                ),
            ),
            FunctionStep(
                function=lambda i: self.assertFalse(
                    self.in_world(playground, "app-misc/C"), f"step {i}"
                ),
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("world", "--check"),
            ),
        )

        self.runEmaintTest(steps, playground)

    def testWorldMissing(self):
        ebuilds = {
            "app-misc/A-1.0": {},
        }

        world = (
            "app-misc/A",
            "app-misc/B",
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=ebuilds,
            world=world,
        )

        emaint = self.cmds["emaint"]
        steps = (
            CommandStep(
                returncode=1,
                command=emaint + ("world", "--check"),
                output=["'app-misc/B' has no available ebuilds"],
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("world", "--fix"),
            ),
            FunctionStep(
                function=lambda i: self.assertTrue(
                    self.in_world(playground, "app-misc/A"), f"step {i}"
                ),
            ),
            FunctionStep(
                function=lambda i: self.assertFalse(
                    self.in_world(playground, "app-misc/B"), f"step {i}"
                ),
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("world", "--check"),
            ),
        )

        self.runEmaintTest(steps, playground)

    @pytest.mark.xfail()
    def testWorldValid(self):
        ebuilds = {
            "app-misc/A-1.0": {},
            "app-misc/B-1.0": {},
        }

        world = (
            "app-misc/A",
            "app/misc/B",
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=ebuilds,
            world=world,
        )

        emaint = self.cmds["emaint"]
        steps = (
            CommandStep(
                returncode=1,
                command=emaint + ("world", "--check"),
                output=["'app/misc/B' is not a valid atom"],
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("world", "--fix"),
            ),
            FunctionStep(
                function=lambda i: self.assertTrue(
                    self.in_world(playground, "app-misc/A"), f"step {i}"
                ),
            ),
            FunctionStep(
                function=lambda i: self.assertFalse(
                    self.in_world(playground, "app-misc/B"), f"step {i}"
                ),
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("world", "--check"),
            ),
        )

        self.runEmaintTest(steps, playground)
