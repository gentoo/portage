# Copyright 2013-2022 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2


import portage
from portage import os, _encodings
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)

from portage.glsa import GlsaFormatException


class SecuritySetTestCase(TestCase):
    glsa_template = """\
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet href="/xsl/glsa.xsl" type="text/xsl"?>
<?xml-stylesheet href="/xsl/guide.xsl" type="text/xsl"?>
<!DOCTYPE glsa SYSTEM "http://www.gentoo.org/dtd/glsa.dtd">
<glsa id="%(glsa_id)s">
  <title>%(pkgname)s: Multiple vulnerabilities</title>
  <synopsis>Multiple vulnerabilities have been found in %(pkgname)s.
  </synopsis>
  <product type="ebuild">%(pkgname)s</product>
  <announced>January 18, 2013</announced>
  <revised count="1">January 18, 2013</revised>
  <bug>55555</bug>
  <access>remote</access>
  <affected>
    <package name="%(cp)s" auto="yes" arch="%(arch)s">
      <unaffected range="ge">%(unaffected_version)s</unaffected>
      <vulnerable range="lt">%(unaffected_version)s</vulnerable>
    </package>
  </affected>
  <background>
    <p>%(pkgname)s is software package.</p>
  </background>
  <description>
    <p>Multiple vulnerabilities have been discovered in %(pkgname)s.
    </p>
  </description>
  <impact type="normal">
    <p>A remote attacker could exploit these vulnerabilities.</p>
  </impact>
  <workaround>
    <p>There is no known workaround at this time.</p>
  </workaround>
  <resolution>
    <p>All %(pkgname)s users should upgrade to the latest version:</p>
    <code>
      # emerge --sync
      # emerge --ask --oneshot --verbose "&gt;=%(cp)s-%(unaffected_version)s"
    </code>
  </resolution>
  <references>
  </references>
</glsa>
"""

    def _must_skip(self):
        try:
            __import__("xml.etree.ElementTree")
            __import__("xml.parsers.expat").parsers.expat.ExpatError
        except (AttributeError, ImportError):
            return "python is missing xml support"

    def write_glsa_test_case(self, glsa_dir, glsa):
        with open(
            os.path.join(glsa_dir, "glsa-" + glsa["glsa_id"] + ".xml"),
            encoding=_encodings["repo.content"],
            mode="w",
        ) as f:
            f.write(self.glsa_template % glsa)

    def testSecuritySet(self):
        skip_reason = self._must_skip()
        if skip_reason:
            self.portage_skip = skip_reason
            self.assertFalse(True, skip_reason)
            return

        ebuilds = {
            "cat/A-vulnerable-2.2": {"KEYWORDS": "x86"},
            "cat/B-not-vulnerable-4.5": {"KEYWORDS": "x86"},
        }

        installed = {
            "cat/A-vulnerable-2.1": {"KEYWORDS": "x86"},
            "cat/B-not-vulnerable-4.4": {"KEYWORDS": "x86"},
        }

        glsas = (
            {
                "glsa_id": "201301-01",
                "pkgname": "A-vulnerable",
                "cp": "cat/A-vulnerable",
                "unaffected_version": "2.2",
                "arch": "*",
            },
            {
                "glsa_id": "201301-02",
                "pkgname": "B-not-vulnerable",
                "cp": "cat/B-not-vulnerable",
                "unaffected_version": "4.4",
                "arch": "*",
            },
            {
                "glsa_id": "201301-03",
                "pkgname": "NotInstalled",
                "cp": "cat/NotInstalled",
                "unaffected_version": "3.5",
                "arch": "*",
            },
        )

        world = ["cat/A"]

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@security"],
                options={},
                success=True,
                mergelist=["cat/A-vulnerable-2.2"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, world=world, debug=False
        )

        try:
            portdb = playground.trees[playground.eroot]["porttree"].dbapi
            glsa_dir = os.path.join(
                portdb.repositories["test_repo"].location, "metadata", "glsa"
            )
            portage.util.ensure_dirs(glsa_dir)
            for glsa in glsas:
                self.write_glsa_test_case(glsa_dir, glsa)

            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testStatelessSecuritySet(self):
        # Tests which don't rely on the GLSA being fixed. This allows
        # testing the format parsing with a bit more flexibility (no
        # need to keep inventing packages).

        skip_reason = self._must_skip()
        if skip_reason:
            self.portage_skip = skip_reason
            self.assertFalse(True, skip_reason)
            return

        ebuilds = {
            "cat/A-vulnerable-2.2": {"KEYWORDS": "x86"},
            "cat/B-not-vulnerable-4.5": {"KEYWORDS": "x86"},
        }

        installed = {
            "cat/A-vulnerable-2.1": {"KEYWORDS": "x86"},
            "cat/B-not-vulnerable-4.4": {"KEYWORDS": "x86"},
        }

        glsas = (
            {
                "glsa_id": "201301-04",
                "pkgname": "A-vulnerable",
                "cp": "cat/A-vulnerable",
                "unaffected_version": "2.2",
                # Use an invalid delimiter (comma)
                "arch": "amd64,sparc",
            },
            {
                "glsa_id": "201301-05",
                "pkgname": "A-vulnerable",
                "cp": "cat/A-vulnerable",
                "unaffected_version": "2.2",
                # Use an invalid arch (~arch)
                "arch": "~amd64",
            },
            {
                "glsa_id": "201301-06",
                "pkgname": "A-vulnerable",
                "cp": "cat/A-vulnerable",
                "unaffected_version": "2.2",
                # Two valid arches followed by an invalid one
                "arch": "amd64 sparc $$$$",
            },
        )

        world = ["cat/A"]

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@security"],
                success=True,
                mergelist=["cat/A-vulnerable-2.2"],
            ),
        )

        # Give each GLSA a clean slate
        for glsa in glsas:
            playground = ResolverPlayground(
                ebuilds=ebuilds, installed=installed, world=world, debug=True
            )

            try:
                portdb = playground.trees[playground.eroot]["porttree"].dbapi
                glsa_dir = os.path.join(
                    portdb.repositories["test_repo"].location, "metadata", "glsa"
                )
                portage.util.ensure_dirs(glsa_dir)

                self.write_glsa_test_case(glsa_dir, glsa)

                with self.assertRaises(GlsaFormatException):
                    for test_case in test_cases:
                        playground.run_TestCase(test_case)
            finally:
                playground.cleanup()
