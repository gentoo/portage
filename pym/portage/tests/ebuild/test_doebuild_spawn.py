# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys
from portage import os
from portage import _shell_quote
from portage.const import EBUILD_SH_BINARY
from portage.package.ebuild.config import config
from portage.package.ebuild.doebuild import spawn as doebuild_spawn
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

class DoebuildSpawnTestCase(TestCase):
	"""
	Invoke portage.package.ebuild.doebuild.spawn() with a
	minimal environment. This gives coverage to some of
	the ebuild execution internals, like ebuild.sh,
	EbuildSpawnProcess, and EbuildIpcDaemon.
	"""

	def testDoebuildSpawn(self):
		playground = ResolverPlayground()
		try:
			settings = config(clone=playground.settings)
			cpv = 'sys-apps/portage-2.1'
			metadata = {}
			settings.setcpv(cpv, mydb=metadata)
			settings['PORTAGE_PYTHON'] = sys.executable
			settings['PORTAGE_BUILDDIR'] = os.path.join(
				settings['PORTAGE_TMPDIR'], cpv)
			settings['T'] = os.path.join(
				settings['PORTAGE_BUILDDIR'], 'temp')
			for x in ('PORTAGE_BUILDDIR', 'T'):
				os.makedirs(settings[x])
			# Create a fake environment, to pretend as if the ebuild
			# has been sourced already.
			open(os.path.join(settings['T'], 'environment'), 'wb')
			for enable_ipc in (False, True):
				if enable_ipc:
					settings['PORTAGE_IPC_DAEMON_ENABLE'] = '1'
				else:
					settings.pop('PORTAGE_IPC_DAEMON_ENABLE', None)
				for phase in ('_internal_test',):
					rval = doebuild_spawn(
						"%s %s" % (_shell_quote(EBUILD_SH_BINARY), phase),
						settings, free=1)
					self.assertEqual(rval, os.EX_OK)
		finally:
			playground.cleanup()
