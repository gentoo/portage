# Copyright 2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools
import io
import tempfile

import portage
from portage import shutil, os
from portage.const import BASH_BINARY, PORTAGE_PYM_PATH
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.tests.util.test_socks5 import AsyncHTTPServer
from portage.util.configparser import ConfigParserError
from portage.util.futures import asyncio
from portage.util.futures.executor.fork import ForkExecutor
from portage.util._async.SchedulerInterface import SchedulerInterface
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.package.ebuild.config import config
from portage.package.ebuild.digestgen import digestgen
from portage.package.ebuild.fetch import (_download_suffix, fetch, FlatLayout,
		FilenameHashLayout, MirrorLayoutConfig)
from _emerge.EbuildFetcher import EbuildFetcher
from _emerge.Package import Package


class EbuildFetchTestCase(TestCase):

	def testEbuildFetch(self):

		user_config = {
			"make.conf":
				(
					'GENTOO_MIRRORS="{scheme}://{host}:{port}"',
				),
		}

		distfiles = {
			'bar': b'bar\n',
			'foo': b'foo\n',
		}

		ebuilds = {
			'dev-libs/A-1': {
				'EAPI': '7',
				'SRC_URI': '''{scheme}://{host}:{port}/distfiles/bar.txt -> bar
					{scheme}://{host}:{port}/distfiles/foo.txt -> foo''',
			},
		}

		loop = SchedulerInterface(global_event_loop())

		def run_async(func, *args, **kwargs):
			with ForkExecutor(loop=loop) as executor:
				return loop.run_until_complete(loop.run_in_executor(executor,
					functools.partial(func, *args, **kwargs)))

		scheme = 'http'
		host = '127.0.0.1'
		content = {}

		content['/distfiles/layout.conf'] = b'[structure]\n0=flat\n'

		for k, v in distfiles.items():
			# mirror path
			content['/distfiles/{}'.format(k)] = v
			# upstream path
			content['/distfiles/{}.txt'.format(k)] = v

		with AsyncHTTPServer(host, content, loop) as server:
			ebuilds_subst = {}
			for cpv, metadata in ebuilds.items():
				metadata = metadata.copy()
				metadata['SRC_URI'] = metadata['SRC_URI'].format(
					scheme=scheme, host=host, port=server.server_port)
				ebuilds_subst[cpv] = metadata

			user_config_subst = user_config.copy()
			for configname, configdata in user_config.items():

				configdata_sub = []
				for line in configdata:
					configdata_sub.append(line.format(
					scheme=scheme, host=host, port=server.server_port))
				user_config_subst[configname] = tuple(configdata_sub)

			playground = ResolverPlayground(ebuilds=ebuilds_subst, distfiles=distfiles, user_config=user_config_subst)
			ro_distdir = tempfile.mkdtemp()
			eubin = os.path.join(playground.eprefix, "usr", "bin")
			try:
				fetchcommand = portage.util.shlex_split(playground.settings['FETCHCOMMAND'])
				fetch_bin = portage.process.find_binary(fetchcommand[0])
				if fetch_bin is None:
					self.skipTest('FETCHCOMMAND not found: {}'.format(playground.settings['FETCHCOMMAND']))
				os.symlink(fetch_bin, os.path.join(eubin, os.path.basename(fetch_bin)))
				resumecommand = portage.util.shlex_split(playground.settings['RESUMECOMMAND'])
				resume_bin = portage.process.find_binary(resumecommand[0])
				if resume_bin is None:
					self.skipTest('RESUMECOMMAND not found: {}'.format(playground.settings['RESUMECOMMAND']))
				if resume_bin != fetch_bin:
					os.symlink(resume_bin, os.path.join(eubin, os.path.basename(resume_bin)))
				root_config = playground.trees[playground.eroot]['root_config']
				portdb = root_config.trees["porttree"].dbapi
				settings = config(clone=playground.settings)

				# Demonstrate that fetch preserves a stale file in DISTDIR when no digests are given.
				foo_uri = {'foo': ('{scheme}://{host}:{port}/distfiles/foo'.format(scheme=scheme, host=host, port=server.server_port),)}
				foo_path = os.path.join(settings['DISTDIR'], 'foo')
				foo_stale_content = b'stale content\n'
				with open(foo_path, 'wb') as f:
					f.write(b'stale content\n')

				self.assertTrue(bool(run_async(fetch, foo_uri, settings, try_mirrors=False)))

				with open(foo_path, 'rb') as f:
					self.assertEqual(f.read(), foo_stale_content)
				with open(foo_path, 'rb') as f:
					self.assertNotEqual(f.read(), distfiles['foo'])

				# Use force=True to update the stale file.
				self.assertTrue(bool(run_async(fetch, foo_uri, settings, try_mirrors=False, force=True)))

				with open(foo_path, 'rb') as f:
					self.assertEqual(f.read(), distfiles['foo'])

				# Test force=True with FEATURES=skiprocheck, using read-only DISTDIR.
				# FETCHCOMMAND is set to temporarily chmod +w DISTDIR. Note that
				# FETCHCOMMAND must perform atomic rename itself due to read-only
				# DISTDIR.
				with open(foo_path, 'wb') as f:
					f.write(b'stale content\n')
				orig_fetchcommand = settings['FETCHCOMMAND']
				orig_distdir_mode = os.stat(settings['DISTDIR']).st_mode
				temp_fetchcommand = os.path.join(eubin, 'fetchcommand')
				with open(temp_fetchcommand, 'w') as f:
					f.write("""
					set -e
					URI=$1
					DISTDIR=$2
					FILE=$3
					trap 'chmod a-w "${DISTDIR}"' EXIT
					chmod ug+w "${DISTDIR}"
					%s
					mv -f "${DISTDIR}/${FILE}.__download__" "${DISTDIR}/${FILE}"
				""" % orig_fetchcommand.replace('${FILE}', '${FILE}.__download__'))
				settings['FETCHCOMMAND'] = '"%s" "%s" "${URI}" "${DISTDIR}" "${FILE}"' % (BASH_BINARY, temp_fetchcommand)
				settings.features.add('skiprocheck')
				settings.features.remove('distlocks')
				os.chmod(settings['DISTDIR'], 0o555)
				try:
					self.assertTrue(bool(run_async(fetch, foo_uri, settings, try_mirrors=False, force=True)))
				finally:
					settings['FETCHCOMMAND'] = orig_fetchcommand
					os.chmod(settings['DISTDIR'], orig_distdir_mode)
					settings.features.remove('skiprocheck')
					settings.features.add('distlocks')
					os.unlink(temp_fetchcommand)

				with open(foo_path, 'rb') as f:
					self.assertEqual(f.read(), distfiles['foo'])

				# Test emirrordist invocation.
				emirrordist_cmd = (portage._python_interpreter, '-b', '-Wd',
					os.path.join(self.bindir, 'emirrordist'),
					'--distfiles', settings['DISTDIR'],
					'--config-root', settings['EPREFIX'],
					'--repositories-configuration', settings.repositories.config_string(),
					'--repo', 'test_repo', '--mirror')

				env = os.environ.copy()
				env['PYTHONPATH'] = ':'.join(
					filter(None, [PORTAGE_PYM_PATH] + os.environ.get('PYTHONPATH', '').split(':')))

				for k in distfiles:
					os.unlink(os.path.join(settings['DISTDIR'], k))

				proc = loop.run_until_complete(asyncio.create_subprocess_exec(*emirrordist_cmd, env=env))
				self.assertEqual(loop.run_until_complete(proc.wait()), 0)

				for k in distfiles:
					with open(os.path.join(settings['DISTDIR'], k), 'rb') as f:
						self.assertEqual(f.read(), distfiles[k])

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

					# Test readonly DISTDIR + skiprocheck, with FETCHCOMMAND set to temporarily chmod DISTDIR
					orig_fetchcommand = settings['FETCHCOMMAND']
					orig_distdir_mode = os.stat(settings['DISTDIR']).st_mode
					for k in settings['AA'].split():
						os.unlink(os.path.join(settings['DISTDIR'], k))
					try:
						os.chmod(settings['DISTDIR'], 0o555)
						settings['FETCHCOMMAND'] = '"%s" -c "chmod ug+w \\"${DISTDIR}\\"; %s; status=\\$?; chmod a-w \\"${DISTDIR}\\"; exit \\$status"' % (BASH_BINARY, orig_fetchcommand.replace('"', '\\"'))
						settings.features.add('skiprocheck')
						settings.features.remove('distlocks')
						self.assertEqual(loop.run_until_complete(async_fetch(pkg, ebuild_path)), 0)
					finally:
						settings['FETCHCOMMAND'] = orig_fetchcommand
						os.chmod(settings['DISTDIR'], orig_distdir_mode)
						settings.features.remove('skiprocheck')
						settings.features.add('distlocks')
			finally:
				shutil.rmtree(ro_distdir)
				playground.cleanup()

	def test_flat_layout(self):
		self.assertTrue(FlatLayout.verify_args(('flat',)))
		self.assertFalse(FlatLayout.verify_args(('flat', 'extraneous-arg')))
		self.assertEqual(FlatLayout().get_path('foo-1.tar.gz'), 'foo-1.tar.gz')

	def test_filename_hash_layout(self):
		self.assertFalse(FilenameHashLayout.verify_args(('filename-hash',)))
		self.assertTrue(FilenameHashLayout.verify_args(('filename-hash', 'SHA1', '8')))
		self.assertFalse(FilenameHashLayout.verify_args(('filename-hash', 'INVALID-HASH', '8')))
		self.assertTrue(FilenameHashLayout.verify_args(('filename-hash', 'SHA1', '4:8:12')))
		self.assertFalse(FilenameHashLayout.verify_args(('filename-hash', 'SHA1', '3')))
		self.assertFalse(FilenameHashLayout.verify_args(('filename-hash', 'SHA1', 'junk')))
		self.assertFalse(FilenameHashLayout.verify_args(('filename-hash', 'SHA1', '4:8:junk')))

		self.assertEqual(FilenameHashLayout('SHA1', '4').get_path('foo-1.tar.gz'),
				'1/foo-1.tar.gz')
		self.assertEqual(FilenameHashLayout('SHA1', '8').get_path('foo-1.tar.gz'),
				'19/foo-1.tar.gz')
		self.assertEqual(FilenameHashLayout('SHA1', '8:16').get_path('foo-1.tar.gz'),
				'19/c3b6/foo-1.tar.gz')
		self.assertEqual(FilenameHashLayout('SHA1', '8:16:24').get_path('foo-1.tar.gz'),
				'19/c3b6/37a94b/foo-1.tar.gz')

	def test_mirror_layout_config(self):
		mlc = MirrorLayoutConfig()
		self.assertEqual(mlc.serialize(), ())
		self.assertIsInstance(mlc.get_best_supported_layout(), FlatLayout)

		conf = '''
[structure]
0=flat
'''
		mlc.read_from_file(io.StringIO(conf))
		self.assertEqual(mlc.serialize(), (('flat',),))
		self.assertIsInstance(mlc.get_best_supported_layout(), FlatLayout)
		self.assertEqual(mlc.get_best_supported_layout().get_path('foo-1.tar.gz'),
				'foo-1.tar.gz')

		conf = '''
[structure]
0=filename-hash SHA1 8:16
1=flat
'''
		mlc.read_from_file(io.StringIO(conf))
		self.assertEqual(mlc.serialize(), (
			('filename-hash', 'SHA1', '8:16'),
			('flat',)
		))
		self.assertIsInstance(mlc.get_best_supported_layout(), FilenameHashLayout)
		self.assertEqual(mlc.get_best_supported_layout().get_path('foo-1.tar.gz'),
				'19/c3b6/foo-1.tar.gz')
		serialized = mlc.serialize()

		# test fallback
		conf = '''
[structure]
0=filename-hash INVALID-HASH 8:16
1=filename-hash SHA1 32
2=flat
'''
		mlc.read_from_file(io.StringIO(conf))
		self.assertEqual(mlc.serialize(), (
			('filename-hash', 'INVALID-HASH', '8:16'),
			('filename-hash', 'SHA1', '32'),
			('flat',)
		))
		self.assertIsInstance(mlc.get_best_supported_layout(), FilenameHashLayout)
		self.assertEqual(mlc.get_best_supported_layout().get_path('foo-1.tar.gz'),
				'19c3b637/foo-1.tar.gz')

		# test deserialization
		mlc.deserialize(serialized)
		self.assertEqual(mlc.serialize(), (
			('filename-hash', 'SHA1', '8:16'),
			('flat',)
		))
		self.assertIsInstance(mlc.get_best_supported_layout(), FilenameHashLayout)
		self.assertEqual(mlc.get_best_supported_layout().get_path('foo-1.tar.gz'),
				'19/c3b6/foo-1.tar.gz')

		# test erraneous input
		conf = '''
[#(*DA*&*F
[structure]
0=filename-hash SHA1 32
'''
		self.assertRaises(ConfigParserError, mlc.read_from_file,
				io.StringIO(conf))

	def test_filename_hash_layout_get_filenames(self):
		layouts = (
			FlatLayout(),
			FilenameHashLayout('SHA1', '4'),
			FilenameHashLayout('SHA1', '8'),
			FilenameHashLayout('SHA1', '8:16'),
			FilenameHashLayout('SHA1', '8:16:24'),
		)
		filename = 'foo-1.tar.gz'

		for layout in layouts:
			distdir = tempfile.mkdtemp()
			try:
				path = os.path.join(distdir, layout.get_path(filename))
				try:
					os.makedirs(os.path.dirname(path))
				except OSError:
					pass

				with open(path, 'wb') as f:
					pass

				self.assertEqual([filename], list(layout.get_filenames(distdir)))
			finally:
				shutil.rmtree(distdir)
