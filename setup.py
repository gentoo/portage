#!/usr/bin/env python
# Copyright 1998-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from distutils.core import setup, Command
from distutils.command.build import build
from distutils.command.build_scripts import build_scripts
from distutils.command.clean import clean
from distutils.command.install import install
from distutils.command.install_data import install_data
from distutils.command.install_lib import install_lib
from distutils.command.install_scripts import install_scripts
from distutils.command.sdist import sdist
from distutils.dep_util import newer
from distutils.dir_util import mkpath, remove_tree
from distutils.util import change_root, subst_vars

import codecs
import collections
import glob
import os
import os.path
import re
import subprocess
import sys


# TODO:
# - smarter rebuilds of docs w/ 'install_docbook' and 'install_epydoc'.

x_scripts = {
	'bin': [
		'bin/ebuild', 'bin/egencache', 'bin/emerge', 'bin/emerge-webrsync',
		'bin/emirrordist', 'bin/portageq', 'bin/quickpkg', 'bin/repoman'
	],
	'sbin': [
		'bin/archive-conf', 'bin/dispatch-conf', 'bin/emaint', 'bin/env-update',
		'bin/etc-update', 'bin/fixpackages', 'bin/regenworld'
	],
}


class x_build(build):
	""" Build command with extra build_man call. """

	def run(self):
		build.run(self)
		self.run_command('build_man')


class build_man(Command):
	""" Perform substitutions in manpages. """

	user_options = [
	]

	def initialize_options(self):
		self.build_base = None

	def finalize_options(self):
		self.set_undefined_options('build',
			('build_base', 'build_base'))

	def run(self):
		for d, files in self.distribution.data_files:
			if not d.startswith('$mandir/'):
				continue

			for source in files:
				target = os.path.join(self.build_base, source)
				mkpath(os.path.dirname(target))

				if not newer(source, target) and not newer(__file__, target):
					continue

				print('copying and updating %s -> %s' % (
					source, target))

				with codecs.open(source, 'r', 'utf8') as f:
					data = f.readlines()
				data[0] = data[0].replace('VERSION',
						self.distribution.get_version())
				with codecs.open(target, 'w', 'utf8') as f:
					f.writelines(data)


class docbook(Command):
	""" Build docs using docbook. """

	user_options = [
		('doc-formats=', None, 'Documentation formats to build (all xmlto formats for docbook are allowed, comma-separated'),
	]

	def initialize_options(self):
		self.doc_formats = 'xhtml,xhtml-nochunks'

	def finalize_options(self):
		self.doc_formats = self.doc_formats.replace(',', ' ').split()

	def run(self):
		if not os.path.isdir('doc/fragment'):
			mkpath('doc/fragment')

		with open('doc/fragment/date', 'w'):
			pass
		with open('doc/fragment/version', 'w') as f:
			f.write('<releaseinfo>%s</releaseinfo>' % self.distribution.get_version())

		for f in self.doc_formats:
			print('Building docs in %s format...' % f)
			subprocess.check_call(['xmlto', '-o', 'doc',
				'-m', 'doc/custom.xsl', f, 'doc/portage.docbook'])


class epydoc(Command):
	""" Build API docs using epydoc. """

	user_options = [
	]

	def initialize_options(self):
		self.build_lib = None

	def finalize_options(self):
		self.set_undefined_options('build_py', ('build_lib', 'build_lib'))

	def run(self):
		self.run_command('build_py')

		print('Building API documentation...')

		process_env = os.environ.copy()
		pythonpath = self.build_lib
		try:
			pythonpath += ':' + process_env['PYTHONPATH']
		except KeyError:
			pass
		process_env['PYTHONPATH'] = pythonpath

		subprocess.check_call(['epydoc', '-o', 'epydoc',
			'--name', self.distribution.get_name(),
			'--url', self.distribution.get_url(),
			'-qq', '--no-frames', '--show-imports',
			'--exclude', 'portage.tests',
			'_emerge', 'portage', 'repoman'],
			env = process_env)
		os.remove('epydoc/api-objects.txt')


class install_docbook(install_data):
	""" install_data for docbook docs """

	user_options = install_data.user_options

	def initialize_options(self):
		install_data.initialize_options(self)
		self.htmldir = None

	def finalize_options(self):
		self.set_undefined_options('install', ('htmldir', 'htmldir'))
		install_data.finalize_options(self)

	def run(self):
		if not os.path.exists('doc/portage.html'):
			self.run_command('docbook')
		self.data_files = [
			(self.htmldir, glob.glob('doc/*.html')),
		]
		install_data.run(self)


class install_epydoc(install_data):
	""" install_data for epydoc docs """

	user_options = install_data.user_options

	def initialize_options(self):
		install_data.initialize_options(self)
		self.htmldir = None

	def finalize_options(self):
		self.set_undefined_options('install', ('htmldir', 'htmldir'))
		install_data.finalize_options(self)

	def run(self):
		if not os.path.exists('epydoc/index.html'):
			self.run_command('epydoc')
		self.data_files = [
			(os.path.join(self.htmldir, 'api'), glob.glob('epydoc/*')),
		]
		install_data.run(self)


class x_build_scripts_custom(build_scripts):
	def finalize_options(self):
		build_scripts.finalize_options(self)
		if 'dir_name' in dir(self):
			self.build_dir = os.path.join(self.build_dir, self.dir_name)
			if self.dir_name in x_scripts:
				self.scripts = x_scripts[self.dir_name]
			else:
				self.scripts = set(self.scripts)
				for other_files in x_scripts.values():
					self.scripts.difference_update(other_files)

	def run(self):
		# group scripts by subdirectory
		split_scripts = collections.defaultdict(list)
		for f in self.scripts:
			dir_name = os.path.dirname(f[len('bin/'):])
			split_scripts[dir_name].append(f)

		base_dir = self.build_dir
		base_scripts = self.scripts
		for d, files in split_scripts.items():
			self.build_dir = os.path.join(base_dir, d)
			self.scripts = files
			self.copy_scripts()

		# restore previous values
		self.build_dir = base_dir
		self.scripts = base_scripts


class x_build_scripts_bin(x_build_scripts_custom):
	dir_name = 'bin'


class x_build_scripts_sbin(x_build_scripts_custom):
	dir_name = 'sbin'


class x_build_scripts_portagebin(x_build_scripts_custom):
	dir_name = 'portage'


class x_build_scripts(build_scripts):
	def initialize_option(self):
		build_scripts.initialize_options(self)

	def finalize_options(self):
		build_scripts.finalize_options(self)

	def run(self):
		self.run_command('build_scripts_bin')
		self.run_command('build_scripts_portagebin')
		self.run_command('build_scripts_sbin')


class x_clean(clean):
	""" clean extended for doc & post-test cleaning """

	def clean_docs(self):
		def get_doc_outfiles():
			for dirpath, dirnames, filenames in os.walk('doc'):
				for f in filenames:
					if f.endswith('.docbook') or f == 'custom.xsl':
						pass
					else:
						yield os.path.join(dirpath, f)

				# do not recurse
				break


		for f in get_doc_outfiles():
			print('removing %s' % repr(f))
			os.remove(f)

		if os.path.isdir('doc/fragment'):
			remove_tree('doc/fragment')

		if os.path.isdir('epydoc'):
			remove_tree('epydoc')

	def clean_tests(self):
		# do not remove incorrect dirs accidentally
		top_dir = os.path.normpath(os.path.join(self.build_lib, '..'))
		cprefix = os.path.commonprefix((self.build_base, top_dir))
		if cprefix != self.build_base:
			return

		bin_dir = os.path.join(top_dir, 'bin')
		if os.path.exists(bin_dir):
			remove_tree(bin_dir)

		conf_dir = os.path.join(top_dir, 'cnf')
		if os.path.islink(conf_dir):
			print('removing %s symlink' % repr(conf_dir))
			os.unlink(conf_dir)

		pni_file = os.path.join(top_dir, '.portage_not_installed')
		if os.path.exists(pni_file):
			print('removing %s' % repr(pni_file))
			os.unlink(pni_file)

	def clean_man(self):
		man_dir = os.path.join(self.build_base, 'man')
		if os.path.exists(man_dir):
			remove_tree(man_dir)

	def run(self):
		if self.all:
			self.clean_tests()
			self.clean_docs()
			self.clean_man()

		clean.run(self)


class x_install(install):
	""" install command with extra Portage paths """

	user_options = install.user_options + [
		# note: $prefix and $exec_prefix are reserved for Python install
		('system-prefix=', None, "Prefix for architecture-independent data"),
		('system-exec-prefix=', None, "Prefix for architecture-specific data"),

		('bindir=', None, "Install directory for main executables"),
		('datarootdir=', None, "Data install root directory"),
		('docdir=', None, "Documentation install directory"),
		('htmldir=', None, "HTML documentation install directory"),
		('mandir=', None, "Manpage root install directory"),
		('portage-base=', 'b', "Portage install base"),
		('portage-bindir=', None, "Install directory for Portage internal-use executables"),
		('portage-datadir=', None, 'Install directory for data files'),
		('sbindir=', None, "Install directory for superuser-intended executables"),
		('sysconfdir=', None, 'System configuration path'),
	]

	# note: the order is important for proper substitution
	paths = [
		('system_prefix', '/usr'),
		('system_exec_prefix', '$system_prefix'),

		('bindir', '$system_exec_prefix/bin'),
		('sbindir', '$system_exec_prefix/sbin'),
		('sysconfdir', '/etc'),

		('datarootdir', '$system_prefix/share'),
		('docdir', '$datarootdir/doc/$package-$version'),
		('htmldir', '$docdir/html'),
		('mandir', '$datarootdir/man'),

		('portage_base', '$system_exec_prefix/lib/portage'),
		('portage_bindir', '$portage_base/bin'),
		('portage_datadir', '$datarootdir/portage'),

		# not customized at the moment
		('logrotatedir', '$sysconfdir/logrotate.d'),
		('portage_confdir', '$portage_datadir/config'),
		('portage_setsdir', '$portage_confdir/sets'),
	]

	def initialize_options(self):
		install.initialize_options(self)

		for key, default in self.paths:
			setattr(self, key, default)
		self.subst_paths = {}

	def finalize_options(self):
		install.finalize_options(self)

		# substitute variables
		new_paths = {
			'package': self.distribution.get_name(),
			'version': self.distribution.get_version(),
		}
		for key, default in self.paths:
			new_paths[key] = subst_vars(getattr(self, key), new_paths)
			setattr(self, key, new_paths[key])
		self.subst_paths = new_paths


class x_install_data(install_data):
	""" install_data with customized path support """

	user_options = install_data.user_options

	def initialize_options(self):
		install_data.initialize_options(self)
		self.build_base = None
		self.paths = None

	def finalize_options(self):
		install_data.finalize_options(self)
		self.set_undefined_options('build',
			('build_base', 'build_base'))
		self.set_undefined_options('install',
			('subst_paths', 'paths'))

	def run(self):
		self.run_command('build_man')

		def process_data_files(df):
			for d, files in df:
				# substitute man sources
				if d.startswith('$mandir/'):
					files = [os.path.join(self.build_base, v) for v in files]

				# substitute variables in path
				d = subst_vars(d, self.paths)
				yield (d, files)

		old_data_files = self.data_files
		self.data_files = process_data_files(self.data_files)

		install_data.run(self)
		self.data_files = old_data_files


class x_install_lib(install_lib):
	""" install_lib command with Portage path substitution """

	user_options = install_lib.user_options

	def initialize_options(self):
		install_lib.initialize_options(self)
		self.portage_base = None
		self.portage_bindir = None
		self.portage_confdir = None

	def finalize_options(self):
		install_lib.finalize_options(self)
		self.set_undefined_options('install',
			('portage_base', 'portage_base'),
			('portage_bindir', 'portage_bindir'),
			('portage_confdir', 'portage_confdir'))

	def install(self):
		ret = install_lib.install(self)

		def rewrite_file(path, val_dict):
			path = os.path.join(self.install_dir, path)
			print('Rewriting %s' % path)
			with codecs.open(path, 'r', 'utf-8') as f:
				data = f.read()

			for varname, val in val_dict.items():
				regexp = r'(?m)^(%s\s*=).*$' % varname
				repl = r'\1 %s' % repr(val)

				data = re.sub(regexp, repl, data)

			with codecs.open(path, 'w', 'utf-8') as f:
				f.write(data)

		rewrite_file('portage/__init__.py', {
			'VERSION': self.distribution.get_version(),
		})
		rewrite_file('portage/const.py', {
			'PORTAGE_BASE_PATH': self.portage_base,
			'PORTAGE_BIN_PATH': self.portage_bindir,
			'PORTAGE_CONFIG_PATH': self.portage_confdir,
		})

		return ret


class x_install_scripts_custom(install_scripts):
	def initialize_options(self):
		install_scripts.initialize_options(self)
		self.root = None

	def finalize_options(self):
		self.set_undefined_options('install',
			('root', 'root'),
			(self.var_name, 'install_dir'))
		install_scripts.finalize_options(self)
		self.build_dir = os.path.join(self.build_dir, self.dir_name)

		# prepend root
		if self.root is not None:
			self.install_dir = change_root(self.root, self.install_dir)


class x_install_scripts_bin(x_install_scripts_custom):
	dir_name = 'bin'
	var_name = 'bindir'


class x_install_scripts_sbin(x_install_scripts_custom):
	dir_name = 'sbin'
	var_name = 'sbindir'


class x_install_scripts_portagebin(x_install_scripts_custom):
	dir_name = 'portage'
	var_name = 'portage_bindir'


class x_install_scripts(install_scripts):
	def initialize_option(self):
		pass

	def finalize_options(self):
		pass

	def run(self):
		self.run_command('install_scripts_bin')
		self.run_command('install_scripts_portagebin')
		self.run_command('install_scripts_sbin')


class x_sdist(sdist):
	""" sdist defaulting to .tar.bz2 format """

	def finalize_options(self):
		if self.formats is None:
			self.formats = ['bztar']

		sdist.finalize_options(self)


class build_tests(x_build_scripts_custom):
	""" Prepare build dir for running tests. """

	def initialize_options(self):
		x_build_scripts_custom.initialize_options(self)
		self.build_base = None
		self.build_lib = None

	def finalize_options(self):
		x_build_scripts_custom.finalize_options(self)
		self.set_undefined_options('build',
			('build_base', 'build_base'),
			('build_lib', 'build_lib'))

		# since we will be writing to $build_lib/.., it is important
		# that we do not leave $build_base
		self.top_dir = os.path.normpath(os.path.join(self.build_lib, '..'))
		cprefix = os.path.commonprefix((self.build_base, self.top_dir))
		if cprefix != self.build_base:
			raise SystemError('build_lib must be a subdirectory of build_base')

		self.build_dir = os.path.join(self.top_dir, 'bin')

	def run(self):
		self.run_command('build_py')

		# install all scripts $build_lib/../bin
		# (we can't do a symlink since we want shebangs corrected)
		x_build_scripts_custom.run(self)

		# symlink 'cnf' directory
		conf_dir = os.path.join(self.top_dir, 'cnf')
		if os.path.exists(conf_dir):
			if not os.path.islink(conf_dir):
				raise SystemError('%s exists and is not a symlink (collision)'
					% repr(conf_dir))
			os.unlink(conf_dir)
		conf_src = os.path.relpath('cnf', self.top_dir)
		print('Symlinking %s -> %s' % (conf_dir, conf_src))
		os.symlink(conf_src, conf_dir)

		# create $build_lib/../.portage_not_installed
		# to enable proper paths in tests
		with open(os.path.join(self.top_dir, '.portage_not_installed'), 'w') as f:
			pass


class test(Command):
	""" run tests """

	user_options = []

	def initialize_options(self):
		self.build_lib = None

	def finalize_options(self):
		self.set_undefined_options('build',
			('build_lib', 'build_lib'))

	def run(self):
		self.run_command('build_tests')
		subprocess.check_call([
			sys.executable, '-bWd',
			os.path.join(self.build_lib, 'portage/tests/runTests.py')
		])


def find_packages():
	for dirpath, dirnames, filenames in os.walk('pym'):
		if '__init__.py' in filenames:
			yield os.path.relpath(dirpath, 'pym')


def find_scripts():
	for dirpath, dirnames, filenames in os.walk('bin'):
		for f in filenames:
			if  f not in ['deprecated-path']:
				yield os.path.join(dirpath, f)


def get_manpages():
	linguas = os.environ.get('LINGUAS')
	if linguas is not None:
		linguas = linguas.split()

	for dirpath, dirnames, filenames in os.walk('man'):
		groups = collections.defaultdict(list)
		for f in filenames:
			fn, suffix = f.rsplit('.', 1)
			groups[suffix].append(os.path.join(dirpath, f))

		topdir = dirpath[len('man/'):]
		if not topdir or linguas is None or topdir in linguas:
			for g, mans in groups.items():
				yield [os.path.join('$mandir', topdir, 'man%s' % g), mans]


setup(
	name = 'portage',
	version = '2.2.18',
	url = 'https://wiki.gentoo.org/wiki/Project:Portage',
	author = 'Gentoo Portage Development Team',
	author_email = 'dev-portage@gentoo.org',

	package_dir = {'': 'pym'},
	packages = list(find_packages()),
	# something to cheat build & install commands
	scripts = list(find_scripts()),

	data_files = list(get_manpages()) + [
		['$sysconfdir', ['cnf/etc-update.conf', 'cnf/dispatch-conf.conf']],
		['$logrotatedir', ['cnf/logrotate.d/elog-save-summary']],
		['$portage_confdir', [
			'cnf/make.conf.example', 'cnf/make.globals', 'cnf/repos.conf']],
		['$portage_setsdir', ['cnf/sets/portage.conf']],
		['$docdir', ['NEWS', 'RELEASE-NOTES']],
		['$portage_base/bin', ['bin/deprecated-path']],
		['$sysconfdir/portage/repo.postsync.d', ['cnf/repo.postsync.d/example']],
	],

	cmdclass = {
		'build': x_build,
		'build_man': build_man,
		'build_scripts': x_build_scripts,
		'build_scripts_bin': x_build_scripts_bin,
		'build_scripts_portagebin': x_build_scripts_portagebin,
		'build_scripts_sbin': x_build_scripts_sbin,
		'build_tests': build_tests,
		'clean': x_clean,
		'docbook': docbook,
		'epydoc': epydoc,
		'install': x_install,
		'install_data': x_install_data,
		'install_docbook': install_docbook,
		'install_epydoc': install_epydoc,
		'install_lib': x_install_lib,
		'install_scripts': x_install_scripts,
		'install_scripts_bin': x_install_scripts_bin,
		'install_scripts_portagebin': x_install_scripts_portagebin,
		'install_scripts_sbin': x_install_scripts_sbin,
		'sdist': x_sdist,
		'test': test,
	},

	classifiers = [
		'Development Status :: 5 - Production/Stable',
		'Environment :: Console',
		'Intended Audience :: System Administrators',
		'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
		'Operating System :: POSIX',
		'Programming Language :: Python',
		'Topic :: System :: Installation/Setup'
	]
)
