# Copyright 2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from __future__ import unicode_literals

import functools
import tempfile

import portage
from portage import shutil, os
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.tests.util.test_socks5 import AsyncHTTPServer
from portage.util.futures.executor.fork import ForkExecutor
from portage.util._async.SchedulerInterface import SchedulerInterface
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.package.ebuild.config import config
from portage.package.ebuild.digestgen import digestgen
from portage.package.ebuild.fetch import _download_suffix
from _emerge.EbuildFetcher import EbuildFetcher
from _emerge.Package import Package


class EbuildFetchTestCase(TestCase):

	def testEbuildFetch(self):

		distfiles = {
			'bar': b'bar\n',
			'foo': b'foo\n',
		}

		ebuilds = {
			'dev-libs/A-1': {
				'EAPI': '7',
				'RESTRICT': 'primaryuri',
				'SRC_URI': '''{scheme}://{host}:{port}/distfiles/bar.txt -> bar
					{scheme}://{host}:{port}/distfiles/foo.txt -> foo''',
			},
		}

		loop = SchedulerInterface(global_event_loop())
		scheme = 'http'
		host = '127.0.0.1'
		content = {}
		for k, v in distfiles.items():
			content['/distfiles/{}.txt'.format(k)] = v

		with AsyncHTTPServer(host, content, loop) as server:
			ebuilds_subst = {}
			for cpv, metadata in ebuilds.items():
				metadata = metadata.copy()
				metadata['SRC_URI'] = metadata['SRC_URI'].format(
					scheme=scheme, host=host, port=server.server_port)
				ebuilds_subst[cpv] = metadata

			playground = ResolverPlayground(ebuilds=ebuilds_subst, distfiles=distfiles)
			ro_distdir = tempfile.mkdtemp()
			try:
				fetchcommand = portage.util.shlex_split(playground.settings['FETCHCOMMAND'])
				fetch_bin = portage.process.find_binary(fetchcommand[0])
				if fetch_bin is None:
					self.skipTest('FETCHCOMMAND not found: {}'.format(playground.settings['FETCHCOMMAND']))
				resumecommand = portage.util.shlex_split(playground.settings['RESUMECOMMAND'])
				resume_bin = portage.process.find_binary(resumecommand[0])
				if resume_bin is None:
					self.skipTest('RESUMECOMMAND not found: {}'.format(playground.settings['RESUMECOMMAND']))
				root_config = playground.trees[playground.eroot]['root_config']
				portdb = root_config.trees["porttree"].dbapi
				settings = config(clone=playground.settings)

				# Tests only work with one ebuild at a time, so the config
				# pool only needs a single config instance.
				class config_pool:
					@staticmethod
					def allocate():
						return settings
					@staticmethod
					def deallocate(settings):
						pass

				def async_fetch(pkg, ebuild_path):
					fetcher = EbuildFetcher(config_pool=config_pool, ebuild_path=ebuild_path,
						fetchonly=False, fetchall=True, pkg=pkg, scheduler=loop)
					fetcher.start()
					return fetcher.async_wait()

				for cpv in ebuilds:
					metadata = dict(zip(Package.metadata_keys,
						portdb.aux_get(cpv, Package.metadata_keys)))

					pkg = Package(built=False, cpv=cpv, installed=False,
						metadata=metadata, root_config=root_config,
						type_name='ebuild')

					settings.setcpv(pkg)
					ebuild_path = portdb.findname(pkg.cpv)
					portage.doebuild_environment(ebuild_path, 'fetch', settings=settings, db=portdb)

					# Test good files in DISTDIR
					for k in settings['AA'].split():
						os.stat(os.path.join(settings['DISTDIR'], k))
					self.assertEqual(loop.run_until_complete(async_fetch(pkg, ebuild_path)), 0)
					for k in settings['AA'].split():
						with open(os.path.join(settings['DISTDIR'], k), 'rb') as f:
							self.assertEqual(f.read(), distfiles[k])

					# Test digestgen with fetch
					os.unlink(os.path.join(os.path.dirname(ebuild_path), 'Manifest'))
					for k in settings['AA'].split():
						os.unlink(os.path.join(settings['DISTDIR'], k))
					with ForkExecutor(loop=loop) as executor:
						self.assertTrue(bool(loop.run_until_complete(
							loop.run_in_executor(executor, functools.partial(
								digestgen, mysettings=settings, myportdb=portdb)))))
					for k in settings['AA'].split():
						with open(os.path.join(settings['DISTDIR'], k), 'rb') as f:
							self.assertEqual(f.read(), distfiles[k])

					# Test missing files in DISTDIR
					for k in settings['AA'].split():
						os.unlink(os.path.join(settings['DISTDIR'], k))
					self.assertEqual(loop.run_until_complete(async_fetch(pkg, ebuild_path)), 0)
					for k in settings['AA'].split():
						with open(os.path.join(settings['DISTDIR'], k), 'rb') as f:
							self.assertEqual(f.read(), distfiles[k])

					# Test empty files in DISTDIR
					for k in settings['AA'].split():
						file_path = os.path.join(settings['DISTDIR'], k)
						with open(file_path, 'wb') as f:
							pass
						self.assertEqual(os.stat(file_path).st_size, 0)
					self.assertEqual(loop.run_until_complete(async_fetch(pkg, ebuild_path)), 0)
					for k in settings['AA'].split():
						with open(os.path.join(settings['DISTDIR'], k), 'rb') as f:
							self.assertEqual(f.read(), distfiles[k])

					# Test non-empty files containing null bytes in DISTDIR
					for k in settings['AA'].split():
						file_path = os.path.join(settings['DISTDIR'], k)
						with open(file_path, 'wb') as f:
							f.write(len(distfiles[k]) * b'\0')
						self.assertEqual(os.stat(file_path).st_size, len(distfiles[k]))
					self.assertEqual(loop.run_until_complete(async_fetch(pkg, ebuild_path)), 0)
					for k in settings['AA'].split():
						with open(os.path.join(settings['DISTDIR'], k), 'rb') as f:
							self.assertEqual(f.read(), distfiles[k])

					# Test PORTAGE_RO_DISTDIRS
					settings['PORTAGE_RO_DISTDIRS'] = '"{}"'.format(ro_distdir)
					orig_fetchcommand = settings['FETCHCOMMAND']
					orig_resumecommand = settings['RESUMECOMMAND']
					try:
						settings['FETCHCOMMAND'] = settings['RESUMECOMMAND'] = ''
						for k in settings['AA'].split():
							file_path = os.path.join(settings['DISTDIR'], k)
							os.rename(file_path, os.path.join(ro_distdir, k))
						self.assertEqual(loop.run_until_complete(async_fetch(pkg, ebuild_path)), 0)
						for k in settings['AA'].split():
							file_path = os.path.join(settings['DISTDIR'], k)
							self.assertTrue(os.path.islink(file_path))
							with open(file_path, 'rb') as f:
								self.assertEqual(f.read(), distfiles[k])
							os.unlink(file_path)
					finally:
						settings.pop('PORTAGE_RO_DISTDIRS')
						settings['FETCHCOMMAND'] = orig_fetchcommand
						settings['RESUMECOMMAND'] = orig_resumecommand

					# Test local filesystem in GENTOO_MIRRORS
					orig_mirrors = settings['GENTOO_MIRRORS']
					orig_fetchcommand = settings['FETCHCOMMAND']
					try:
						settings['GENTOO_MIRRORS'] = ro_distdir
						settings['FETCHCOMMAND'] = settings['RESUMECOMMAND'] = ''
						self.assertEqual(loop.run_until_complete(async_fetch(pkg, ebuild_path)), 0)
						for k in settings['AA'].split():
							with open(os.path.join(settings['DISTDIR'], k), 'rb') as f:
								self.assertEqual(f.read(), distfiles[k])
					finally:
						settings['GENTOO_MIRRORS'] = orig_mirrors
						settings['FETCHCOMMAND'] = orig_fetchcommand
						settings['RESUMECOMMAND'] = orig_resumecommand

					# Test readonly DISTDIR
					orig_distdir_mode = os.stat(settings['DISTDIR']).st_mode
					try:
						os.chmod(settings['DISTDIR'], 0o555)
						self.assertEqual(loop.run_until_complete(async_fetch(pkg, ebuild_path)), 0)
						for k in settings['AA'].split():
							with open(os.path.join(settings['DISTDIR'], k), 'rb') as f:
								self.assertEqual(f.read(), distfiles[k])
					finally:
						os.chmod(settings['DISTDIR'], orig_distdir_mode)

					# Test parallel-fetch mode
					settings['PORTAGE_PARALLEL_FETCHONLY'] = '1'
					try:
						self.assertEqual(loop.run_until_complete(async_fetch(pkg, ebuild_path)), 0)
						for k in settings['AA'].split():
							with open(os.path.join(settings['DISTDIR'], k), 'rb') as f:
								self.assertEqual(f.read(), distfiles[k])
						for k in settings['AA'].split():
							os.unlink(os.path.join(settings['DISTDIR'], k))
						self.assertEqual(loop.run_until_complete(async_fetch(pkg, ebuild_path)), 0)
						for k in settings['AA'].split():
							with open(os.path.join(settings['DISTDIR'], k), 'rb') as f:
								self.assertEqual(f.read(), distfiles[k])
					finally:
						settings.pop('PORTAGE_PARALLEL_FETCHONLY')

					# Test RESUMECOMMAND
					orig_resume_min_size = settings['PORTAGE_FETCH_RESUME_MIN_SIZE']
					try:
						settings['PORTAGE_FETCH_RESUME_MIN_SIZE'] = '2'
						for k in settings['AA'].split():
							file_path = os.path.join(settings['DISTDIR'], k)
							os.unlink(file_path)
							with open(file_path + _download_suffix, 'wb') as f:
								f.write(distfiles[k][:2])
						self.assertEqual(loop.run_until_complete(async_fetch(pkg, ebuild_path)), 0)
						for k in settings['AA'].split():
							with open(os.path.join(settings['DISTDIR'], k), 'rb') as f:
								self.assertEqual(f.read(), distfiles[k])
					finally:
						settings['PORTAGE_FETCH_RESUME_MIN_SIZE'] = orig_resume_min_size
			finally:
				shutil.rmtree(ro_distdir)
				playground.cleanup()
