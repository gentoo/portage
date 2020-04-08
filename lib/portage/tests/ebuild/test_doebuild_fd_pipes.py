# Copyright 2013-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.package.ebuild._ipc.QueryCommand import QueryCommand
from portage.util._async.ForkProcess import ForkProcess
from portage.util._async.TaskScheduler import TaskScheduler
from _emerge.Package import Package
from _emerge.PipeReader import PipeReader

class DoebuildProcess(ForkProcess):

	__slots__ = ('doebuild_kwargs', 'doebuild_pargs')

	def _run(self):
		return portage.doebuild(*self.doebuild_pargs, **self.doebuild_kwargs)

class DoebuildFdPipesTestCase(TestCase):

	def testDoebuild(self):
		"""
		Invoke portage.doebuild() with the fd_pipes parameter, and
		check that the expected output appears in the pipe. This
		functionality is not used by portage internally, but it is
		supported for API consumers (see bug #475812).
		"""

		output_fd = 200
		ebuild_body = ['S=${WORKDIR}']
		for phase_func in ('pkg_info', 'pkg_nofetch', 'pkg_pretend',
			'pkg_setup', 'src_unpack', 'src_prepare', 'src_configure',
			'src_compile', 'src_test', 'src_install'):
			ebuild_body.append(('%s() { echo ${EBUILD_PHASE}'
				' 1>&%s; }') % (phase_func, output_fd))

		ebuild_body.append('')
		ebuild_body = '\n'.join(ebuild_body)

		ebuilds = {
			'app-misct/foo-1': {
				'EAPI'      : '5',
				"MISC_CONTENT": ebuild_body,
			}
		}

		# Override things that may be unavailable, or may have portability
		# issues when running tests in exotic environments.
		#   prepstrip - bug #447810 (bash read builtin EINTR problem)
		true_symlinks = ("find", "prepstrip", "sed", "scanelf")
		true_binary = portage.process.find_binary("true")
		self.assertEqual(true_binary is None, False,
			"true command not found")

		dev_null = open(os.devnull, 'wb')
		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			QueryCommand._db = playground.trees
			root_config = playground.trees[playground.eroot]['root_config']
			portdb = root_config.trees["porttree"].dbapi
			settings = portage.config(clone=playground.settings)
			if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
				settings["__PORTAGE_TEST_HARDLINK_LOCKS"] = \
					os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"]
				settings.backup_changes("__PORTAGE_TEST_HARDLINK_LOCKS")

			settings.features.add("noauto")
			settings.features.add("test")
			settings['PORTAGE_PYTHON'] = portage._python_interpreter
			settings['PORTAGE_QUIET'] = "1"
			settings['PYTHONDONTWRITEBYTECODE'] = os.environ.get("PYTHONDONTWRITEBYTECODE", "")

			fake_bin = os.path.join(settings["EPREFIX"], "bin")
			portage.util.ensure_dirs(fake_bin)
			for x in true_symlinks:
				os.symlink(true_binary, os.path.join(fake_bin, x))

			settings["__PORTAGE_TEST_PATH_OVERRIDE"] = fake_bin
			settings.backup_changes("__PORTAGE_TEST_PATH_OVERRIDE")

			cpv = 'app-misct/foo-1'
			metadata = dict(zip(Package.metadata_keys,
				portdb.aux_get(cpv, Package.metadata_keys)))

			pkg = Package(built=False, cpv=cpv, installed=False,
				metadata=metadata, root_config=root_config,
				type_name='ebuild')
			settings.setcpv(pkg)
			ebuildpath = portdb.findname(cpv)
			self.assertNotEqual(ebuildpath, None)

			for phase in ('info', 'nofetch',
				 'pretend', 'setup', 'unpack', 'prepare', 'configure',
				 'compile', 'test', 'install', 'qmerge', 'clean', 'merge'):

				pr, pw = os.pipe()

				producer = DoebuildProcess(doebuild_pargs=(ebuildpath, phase),
					doebuild_kwargs={"settings" : settings,
						"mydbapi": portdb, "tree": "porttree",
						"vartree": root_config.trees["vartree"],
						"fd_pipes": {
							1: dev_null.fileno(),
							2: dev_null.fileno(),
							output_fd: pw,
						},
						"prev_mtimes": {}})

				consumer = PipeReader(
					input_files={"producer" : pr})

				task_scheduler = TaskScheduler(iter([producer, consumer]),
					max_jobs=2)

				try:
					task_scheduler.start()
				finally:
					# PipeReader closes pr
					os.close(pw)

				task_scheduler.wait()
				output = portage._unicode_decode(
					consumer.getvalue()).rstrip("\n")

				if task_scheduler.returncode != os.EX_OK:
					portage.writemsg(output, noiselevel=-1)

				self.assertEqual(task_scheduler.returncode, os.EX_OK)

				if phase not in ('clean', 'merge', 'qmerge'):
					self.assertEqual(phase, output)

		finally:
			dev_null.close()
			playground.cleanup()
			QueryCommand._db = None
