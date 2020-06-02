# Copyright 2010-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import textwrap

from portage import os
from portage import _python_interpreter
from portage import _shell_quote
from portage.const import EBUILD_SH_BINARY
from portage.package.ebuild.config import config
from portage.package.ebuild.doebuild import spawn as doebuild_spawn
from portage.package.ebuild._spawn_nofetch import spawn_nofetch
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util._async.SchedulerInterface import SchedulerInterface
from portage.util._eventloop.global_event_loop import global_event_loop
from _emerge.EbuildPhase import EbuildPhase
from _emerge.MiscFunctionsProcess import MiscFunctionsProcess
from _emerge.Package import Package

class DoebuildSpawnTestCase(TestCase):
	"""
	Invoke portage.package.ebuild.doebuild.spawn() with a
	minimal environment. This gives coverage to some of
	the ebuild execution internals, like ebuild.sh,
	AbstractEbuildProcess, and EbuildIpcDaemon.
	"""

	def testDoebuildSpawn(self):

		ebuild_body = textwrap.dedent("""
			pkg_nofetch() { : ; }
		""")

		ebuilds = {
			'sys-apps/portage-2.1': {
				'EAPI'      : '2',
				'IUSE'      : 'build doc epydoc python3 selinux',
				'KEYWORDS'  : 'x86',
				'LICENSE'   : 'GPL-2',
				'RDEPEND'   : '>=app-shells/bash-3.2_p17 >=dev-lang/python-2.6',
				'SLOT'      : '0',
				"MISC_CONTENT": ebuild_body,
			}
		}

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			root_config = playground.trees[playground.eroot]['root_config']
			portdb = root_config.trees["porttree"].dbapi
			settings = config(clone=playground.settings)
			if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
				settings["__PORTAGE_TEST_HARDLINK_LOCKS"] = \
					os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"]
				settings.backup_changes("__PORTAGE_TEST_HARDLINK_LOCKS")

			cpv = 'sys-apps/portage-2.1'
			metadata = dict(zip(Package.metadata_keys,
				portdb.aux_get(cpv, Package.metadata_keys)))

			pkg = Package(built=False, cpv=cpv, installed=False,
				metadata=metadata, root_config=root_config,
				type_name='ebuild')
			settings.setcpv(pkg)
			settings['PORTAGE_PYTHON'] = _python_interpreter
			settings['PORTAGE_BUILDDIR'] = os.path.join(
				settings['PORTAGE_TMPDIR'], cpv)
			settings['PYTHONDONTWRITEBYTECODE'] = os.environ.get('PYTHONDONTWRITEBYTECODE', '')
			settings['HOME'] = os.path.join(
				settings['PORTAGE_BUILDDIR'], 'homedir')
			settings['T'] = os.path.join(
				settings['PORTAGE_BUILDDIR'], 'temp')
			for x in ('PORTAGE_BUILDDIR', 'HOME', 'T'):
				os.makedirs(settings[x])
			# Create a fake environment, to pretend as if the ebuild
			# has been sourced already.
			open(os.path.join(settings['T'], 'environment'), 'wb').close()

			scheduler = SchedulerInterface(global_event_loop())
			for phase in ('_internal_test',):

				# Test EbuildSpawnProcess by calling doebuild.spawn() with
				# returnpid=False. This case is no longer used by portage
				# internals since EbuildPhase is used instead and that passes
				# returnpid=True to doebuild.spawn().
				rval = doebuild_spawn("%s %s" % (_shell_quote(
					os.path.join(settings["PORTAGE_BIN_PATH"],
					os.path.basename(EBUILD_SH_BINARY))), phase),
					settings, free=1)
				self.assertEqual(rval, os.EX_OK)

				ebuild_phase = EbuildPhase(background=False,
					phase=phase, scheduler=scheduler,
					settings=settings)
				ebuild_phase.start()
				ebuild_phase.wait()
				self.assertEqual(ebuild_phase.returncode, os.EX_OK)

			ebuild_phase = MiscFunctionsProcess(background=False,
				commands=['success_hooks'],
				scheduler=scheduler, settings=settings)
			ebuild_phase.start()
			ebuild_phase.wait()
			self.assertEqual(ebuild_phase.returncode, os.EX_OK)

			spawn_nofetch(portdb, portdb.findname(cpv), settings=settings)
		finally:
			playground.cleanup()
