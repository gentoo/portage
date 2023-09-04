# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.dep import Atom
from portage.dep.libc import strip_libc_deps
from portage.tests import TestCase


class LibcUtilStripDeps(TestCase):
    def testStripSimpleDeps(self):
        """
        Test that we strip a basic libc dependency out and return
        a list of dependencies without it in there.
        """

        libc_dep = [Atom("=sys-libs/glibc-2.38")]

        original_deps = (
            [
                Atom("=sys-libs/glibc-2.38"),
                Atom("=app-misc/foo-1.2.3"),
            ],
            [
                Atom("=sys-libs/glibc-2.38"),
            ],
            [
                Atom("=app-misc/foo-1.2.3"),
                Atom("=app-misc/bar-1.2.3"),
            ],
        )

        for deplist in original_deps:
            strip_libc_deps(deplist, libc_dep)

            self.assertFalse(
                all(libc in deplist for libc in libc_dep),
                "Stripped deplist contains a libc candidate",
            )

    def testStripComplexRealizedDeps(self):
        """
        Test that we strip pathological libc dependencies out and return
        a list of dependencies without it in there.
        """

        # This shouldn't really happen for a 'realized' dependency, but
        # we shouldn't crash if it happens anyway.
        libc_dep = [Atom("=sys-libs/glibc-2.38*[p]")]

        original_deps = (
            [
                Atom("=sys-libs/glibc-2.38[x]"),
                Atom("=app-misc/foo-1.2.3"),
            ],
            [
                Atom("=sys-libs/glibc-2.38[p]"),
            ],
            [
                Atom("=app-misc/foo-1.2.3"),
                Atom("=app-misc/bar-1.2.3"),
            ],
        )

        for deplist in original_deps:
            strip_libc_deps(deplist, libc_dep)

            self.assertFalse(
                all(libc in deplist for libc in libc_dep),
                "Stripped deplist contains a libc candidate",
            )

    def testStripNonRealizedDeps(self):
        """
        Check that we strip non-realized libc deps.
        """

        libc_dep = [Atom("sys-libs/glibc:2.2=")]
        original_deps = [Atom(">=sys-libs/glibc-2.38-r7")]

        strip_libc_deps(original_deps, libc_dep)
        self.assertFalse(original_deps, "(g)libc dep was not stripped")
