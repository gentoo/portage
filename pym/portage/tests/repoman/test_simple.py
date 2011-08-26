# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import shutil
import subprocess
import sys
import time

import portage
from portage import os
from portage import _unicode_decode
from portage.const import PORTAGE_BASE_PATH, PORTAGE_BIN_PATH, PORTAGE_PYM_PATH
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs

class SimpleRepomanTestCase(TestCase):

	def _must_skip(self):
		xmllint = find_binary("xmllint")
		if not xmllint:
			return "xmllint not found"

		try:
			__import__("xml.etree.ElementTree")
			__import__("xml.parsers.expat").parsers.expat.ExpatError
		except (AttributeError, ImportError):
			return "python is missing xml support"

	def testSimple(self):

		skip_reason = self._must_skip()
		if skip_reason:
			self.portage_skip = skip_reason
			self.assertFalse(True, skip_reason)
			return

		copyright_header = """# Copyright 1999-%s Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $
""" % time.gmtime().tm_year

		profiles = (
			("x86", "default/linux/x86/test_profile", "stable"),
		)

		ebuilds = {
			"dev-libs/A-1": {
				"COPYRIGHT_HEADER" : copyright_header,
				"DESCRIPTION" : "Desc goes here",
				"EAPI" : "4",
				"HOMEPAGE" : "http://example.com",
				"IUSE" : "flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
				"RDEPEND": "flag? ( dev-libs/B[flag] )",
			},
			"dev-libs/B-1": {
				"COPYRIGHT_HEADER" : copyright_header,
				"DESCRIPTION" : "Desc goes here",
				"EAPI" : "4",
				"HOMEPAGE" : "http://example.com",
				"IUSE" : "flag",
				"KEYWORDS": "x86",
				"LICENSE": "GPL-2",
			},
		}
		licenses = ["GPL-2"]
		arch_list = ["x86"]
		metadata_dtd = os.path.join(PORTAGE_BASE_PATH, "cnf/metadata.dtd")
		metadata_xml_template = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pkgmetadata SYSTEM "http://www.gentoo.org/dtd/metadata.dtd">
<pkgmetadata>
<herd>%(herd)s</herd>
<maintainer>
<email>maintainer-needed@gentoo.org</email>
<description>Description of the maintainership</description>
</maintainer>
<longdescription>Long description of the package</longdescription>
<use>
%(flags)s
</use>
</pkgmetadata>
"""

		metadata_xml_files = (
			(
				"dev-libs/A",
				{
					"herd" : "no-herd",
					"flags" : "<flag name='flag'>Description of how USE='flag' affects this package</flag>",
				},
			),
			(
				"dev-libs/B",
				{
					"herd" : "no-herd",
					"flags" : "<flag name='flag'>Description of how USE='flag' affects this package</flag>",
				},
			),
		)

		use_desc = (
			("flag", "Description of how USE='flag' affects packages"),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		settings = playground.settings
		eprefix = settings["EROOT"]
		distdir = os.path.join(eprefix, "distdir")
		portdir = settings["PORTDIR"]
		profiles_dir = os.path.join(portdir, "profiles")
		license_dir = os.path.join(portdir, "licenses")
		env = os.environ.copy()
		pythonpath = env.get("PYTHONPATH")
		if pythonpath is not None and not pythonpath.strip():
			pythonpath = None
		if pythonpath is None:
			pythonpath = ""
		else:
			pythonpath = ":" + pythonpath
		pythonpath = PORTAGE_PYM_PATH + pythonpath
		env['PYTHONPATH'] = pythonpath
		env.update({
			"__REPOMAN_TEST_EPREFIX" : eprefix,
			"DISTDIR" : distdir,
			"PORTDIR" : portdir,
		})
		dirs = [license_dir, profiles_dir, distdir]
		try:
			for d in dirs:
				ensure_dirs(d)
			with open(os.path.join(profiles_dir, "profiles.desc"), 'w') as f:
				for x in profiles:
					f.write("%s %s %s\n" % x)
			for x in licenses:
				open(os.path.join(license_dir, x), 'wb').close()
			with open(os.path.join(profiles_dir, "arch.list"), 'w') as f:
				for x in arch_list:
					f.write("%s\n" % x)
			with open(os.path.join(profiles_dir, "use.desc"), 'w') as f:
				for k, v in use_desc:
					f.write("%s - %s\n" % (k, v))
			for cp, xml_data in metadata_xml_files:
				with open(os.path.join(portdir, cp, "metadata.xml"), 'w') as f:
					f.write(metadata_xml_template % xml_data)
			# repoman checks metadata.dtd for recent CTIME, so copy the file in
			# order to ensure that the CTIME is current
			shutil.copyfile(metadata_dtd, os.path.join(distdir, "metadata.dtd"))
			for cwd in ("", "dev-libs", "dev-libs/A", "dev-libs/B"):
				cwd = os.path.join(portdir, cwd)
				proc = subprocess.Popen([portage._python_interpreter, "-Wd",
					os.path.join(PORTAGE_BIN_PATH, "repoman"), "full"],
					cwd=cwd, env=env, stdout=subprocess.PIPE)
				output = proc.stdout.readlines()
				proc.wait()
				proc.stdout.close()
				if proc.returncode != os.EX_OK:
					for line in output:
						sys.stderr.write(_unicode_decode(line))

				self.assertEqual(os.EX_OK, proc.returncode, "repoman failed")
		finally:
			playground.cleanup()
