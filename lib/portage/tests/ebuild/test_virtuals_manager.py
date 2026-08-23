# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import shutil
import tempfile

import portage
from portage.dep import Atom
from portage.package.ebuild._config.VirtualsManager import VirtualsManager
from portage.tests import TestCase


class _FakeVartree:
    def __init__(self, provides=None):
        self._provides = provides or {}

    def get_all_provides(self):
        return self._provides


class VirtualsManagerTestCase(TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._internal_caller = portage._internal_caller
        portage._internal_caller = True

    def tearDown(self):
        portage._internal_caller = self._internal_caller
        shutil.rmtree(self._tmpdir)

    def _profile(self, name, virtuals=None):
        """
        Create a profile directory, optionally containing a virtuals file
        with the given lines, and return its path.
        """
        profile_path = os.path.join(self._tmpdir, name)
        os.mkdir(profile_path)
        if virtuals is not None:
            with open(os.path.join(profile_path, "virtuals"), "w") as f:
                f.write("".join(f"{line}\n" for line in virtuals))
        return profile_path

    def _manager(self, profiles, provides=None):
        """
        Return a VirtualsManager for the given profiles, with _treeVirtuals
        populated from a fake vartree so that getvirtuals() can be called.
        """
        virtuals_manager = VirtualsManager(profiles)
        virtuals_manager._populate_treeVirtuals(_FakeVartree(provides))
        return virtuals_manager

    def testDirVirtuals(self):
        profile = self._profile(
            "profile", ["virtual/editor app-editors/vim app-editors/emacs"]
        )
        virtuals_manager = VirtualsManager([profile])
        # The provider list is reversed, so that providers from the profile
        # read last come first.
        self.assertEqual(
            virtuals_manager._dirVirtuals,
            {
                Atom("virtual/editor"): [
                    Atom("app-editors/emacs"),
                    Atom("app-editors/vim"),
                ]
            },
        )

    def testDirVirtualsIncremental(self):
        parent = self._profile(
            "parent", ["virtual/editor app-editors/vim app-editors/emacs"]
        )
        child = self._profile("child", ["virtual/editor -app-editors/vim"])
        virtuals_manager = VirtualsManager([parent, child])
        self.assertEqual(
            virtuals_manager._dirVirtuals,
            {Atom("virtual/editor"): [Atom("app-editors/emacs")]},
        )

    def testDirVirtualsInvalidAtom(self):
        profile = self._profile("profile", ["virtual/editor !app-editors/vim"])
        virtuals_manager = VirtualsManager([profile])
        self.assertEqual(virtuals_manager._dirVirtuals, {})

    def testGetVirtuals(self):
        profile = self._profile("profile", ["virtual/editor app-editors/vim"])
        virtuals_manager = self._manager([profile])
        self.assertEqual(
            virtuals_manager.getvirtuals(),
            {Atom("virtual/editor"): [Atom("app-editors/vim")]},
        )

    def testGetVirtualsInstalled(self):
        profile = self._profile(
            "profile", ["virtual/editor app-editors/vim app-editors/emacs"]
        )
        # An installed provider is preferred over one that is not installed.
        virtuals_manager = self._manager(
            [profile], {"virtual/editor": ["app-editors/vim-9"]}
        )
        self.assertEqual(
            virtuals_manager.getvirtuals()[Atom("virtual/editor")],
            [Atom("app-editors/vim"), Atom("app-editors/emacs")],
        )

    def testGetVirtsP(self):
        profile = self._profile("profile", ["virtual/editor app-editors/vim"])
        virtuals_manager = self._manager([profile])
        self.assertEqual(
            virtuals_manager.get_virts_p(),
            {"editor": [Atom("app-editors/vim")]},
        )
