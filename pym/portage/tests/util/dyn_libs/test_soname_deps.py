# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util._dyn_libs.NeededEntry import NeededEntry
from portage.util._dyn_libs.soname_deps import SonameDepsProcessor


class SonameDepsProcessorTestCase(TestCase):

	def testInternalLibsWithoutSoname(self):
		"""
		Test handling of internal libraries that lack an soname, which are
		resolved via DT_RUNPATH, see ebtables for example (bug 646190).
		"""
		needed_elf_2 = """
X86_64;/sbin/ebtables;;/lib64/ebtables;libebt_802_3.so,libebtable_broute.so,libc.so.6;x86_64
X86_64;/lib64/ebtables/libebtable_broute.so;;;libc.so.6;x86_64
X86_64;/lib64/ebtables/libebt_802_3.so;;;libc.so.6;x86_64
"""
		soname_deps = SonameDepsProcessor('', '')

		for line in needed_elf_2.splitlines():
			if not line:
				continue
			entry = NeededEntry.parse(None, line)
			soname_deps.add(entry)

		self.assertEqual(soname_deps.provides, None)
		# Prior to the fix for bug 646190, REQUIRES contained references to
		# the internal libebt* libraries which are resolved via a DT_RUNPATH
		# entry referring to the /lib64/ebtables directory that contains the
		# internal libraries.
		self.assertEqual(soname_deps.requires, 'x86_64: libc.so.6\n')
