#!/usr/bin/env python
# Copyright 1998-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

try:
	from setuptools.core import setup, Command, Extension
	from setuptools.command.build import build
	from setuptools.command.build_ext import build_ext as _build_ext
	from setuptools.command.build_scripts import build_scripts
	from setuptools.command.clean import clean
	from setuptools.command.install import install
	from setuptools.command.install_data import install_data
	from setuptools.command.install_lib import install_lib
	from setuptools.command.install_scripts import install_scripts
	from setuptools.command.sdist import sdist
	from setuptools.dep_util import newer
	from setuptools.dir_util import mkpath, remove_tree
	from setuptools.util import change_root, subst_vars
except ImportError:
	from distutils.core import setup, Command, Extension
	from distutils.command.build import build
	from distutils.command.build_ext import build_ext as _build_ext
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
import itertools
import os
import os.path
import platform
import re
import subprocess
import sys

autodetect_pip = os.path.basename(os.environ.get("_", "")) == "pip" or os.path.basename(
	os.path.dirname(__file__)
).startswith("pip-")
venv_prefix = "" if sys.prefix == sys.base_prefix else sys.prefix
create_entry_points = bool(autodetect_pip or venv_prefix)
with open(os.path.join(os.path.dirname(__file__), 'README'), 'rt') as f:
	long_description = f.read()

# TODO:
# - smarter rebuilds of docs w/ 'install_docbook' and 'install_apidoc'.

# Dictionary of scripts.  The structure is
#   key   = location in filesystem to install the scripts
#   value = list of scripts, path relative to top source directory
x_scripts = {
	'bin': [
		'bin/ebuild', 'bin/egencache', 'bin/emerge', 'bin/emerge-webrsync',
		'bin/emirrordist', 'bin/glsa-check', 'bin/portageq', 'bin/quickpkg',
	],
	'sbin': [
		'bin/archive-conf', 'bin/dispatch-conf', 'bin/emaint', 'bin/env-update',
		'bin/etc-update', 'bin/fixpackages', 'bin/regenworld'
	],
}

# Dictionary custom modules written in C/C++ here.  The structure is
#   key   = module name
#   value = list of C/C++ source code, path relative to top source directory
x_c_helpers = {
	'portage.util.libc' : [
		'src/portage_util_libc.c',
	],
}

if platform.system() == 'Linux':
	x_c_helpers.update({
		'portage.util.file_copy.reflink_linux': [
			'src/portage_util_file_copy_reflink_linux.c',
		],
	})


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


class apidoc(Command):
	""" Build API docs using apidoc. """

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

		subprocess.check_call(['make', '-C', 'doc/api', 'html'],
			env = process_env)


class install_docbook(install_data):
	""" install_data for docbook docs """

	user_options = install_data.user_options + [
		('htmldir=', None, "HTML documentation install directory"),
	]

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


class install_apidoc(install_data):
	""" install_data for apidoc docs """

	user_options = install_data.user_options + [
		('htmldir=', None, "HTML documentation install directory"),
	]

	def initialize_options(self):
		install_data.initialize_options(self)
		self.htmldir = None

	def finalize_options(self):
		self.set_undefined_options('install', ('htmldir', 'htmldir'))
		install_data.finalize_options(self)

	def run(self):
		if not os.path.exists('doc/api/build/html/index.html'):
			self.run_command('apidoc')
		self.data_files = [
			(os.path.join(self.htmldir, 'api'), glob.glob('doc/api/build/html/*.html') + glob.glob('doc/api/build/html/*.js')),
			(os.path.join(self.htmldir, 'api/_static'), glob.glob('doc/api/build/html/_static/*')),
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
				if not (create_entry_points and self.dir_name == "portage"):
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

	@staticmethod
	def clean_docs():
		def get_doc_outfiles():
			for dirpath, _dirnames, filenames in os.walk('doc'):
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

		if os.path.isdir('doc/api/build'):
			remove_tree('doc/api/build')

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
		for key, _default in self.paths:
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
		def re_sub_file(path, pattern, repl):
			print('Rewriting %s' % path)
			with codecs.open(path, 'r', 'utf-8') as f:
				data = f.read()
			data = re.sub(pattern, repl, data, flags=re.MULTILINE)
			with codecs.open(path, 'w', 'utf-8') as f:
				f.write(data)

		if create_entry_points:
			re_sub_file('cnf/repos.conf', r'= /', '= %(EPREFIX)s/')
			re_sub_file('cnf/make.globals', r'DIR="/', 'DIR="${EPREFIX}/')

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

		def re_sub_file(path, pattern_repl_items):
			path = os.path.join(self.install_dir, path)
			print("Rewriting %s" % path)
			with codecs.open(path, "r", "utf-8") as f:
				data = f.read()
			for pattern, repl in pattern_repl_items:
				data = re.sub(pattern, repl, data, flags=re.MULTILINE)
			with codecs.open(path, "w", "utf-8") as f:
				f.write(data)

		val_dict = {}
		if create_entry_points:
			val_dict.update(
				{
					"GLOBAL_CONFIG_PATH": self.portage_confdir,
				}
			)
			re_sub_file(
				"portage/const.py",
				(
					(
						r"^(PORTAGE_BASE_PATH\s*=\s*)(.*)",
						lambda m: "{}{}".format(
							m.group(1),
							'os.path.realpath(os.path.join(__file__, "../../usr/lib/portage"))',
						),
					),
					(
						r"^(EPREFIX\s*=\s*)(.*)",
						lambda m: "{}{}".format(
							m.group(1),
							'os.path.realpath(os.path.join(__file__, "../.."))',
						),
					),
				),
			)
		else:
			val_dict.update(
				{
					"PORTAGE_BASE_PATH": self.portage_base,
					"PORTAGE_BIN_PATH": self.portage_bindir,
				}
			)
		rewrite_file("portage/const.py", val_dict)

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
	""" sdist defaulting to .tar.bz2 format, and archive files owned by root """

	def initialize_options(self):
		super().initialize_options()
		self.formats = ['xztar']

	def finalize_options(self):
		if self.owner is None:
			self.owner = 'root'
		if self.group is None:
			self.group = 'root'

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
		with open(os.path.join(self.top_dir, '.portage_not_installed'), 'w'):
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
	for dirpath, _dirnames, filenames in os.walk('lib'):
		if '__init__.py' in filenames:
			yield os.path.relpath(dirpath, 'lib')


def find_scripts():
	for dirpath, _dirnames, filenames in os.walk('bin'):
		for f in filenames:
			if  f not in ['deprecated-path']:
				yield os.path.join(dirpath, f)


def get_manpages():
	linguas = os.environ.get('LINGUAS')
	if linguas is not None:
		linguas = linguas.split()

	for dirpath, _dirnames, filenames in os.walk('man'):
		groups = collections.defaultdict(list)
		for f in filenames:
			_fn, suffix = f.rsplit('.', 1)
			groups[suffix].append(os.path.join(dirpath, f))

		topdir = dirpath[len('man/'):]
		if not topdir or linguas is None or topdir in linguas:
			for g, mans in groups.items():
				yield [os.path.join('$mandir', topdir, 'man%s' % g), mans]


class build_ext(_build_ext):
	user_options = _build_ext.user_options + [
		('portage-ext-modules', None,
		 "enable portage's C/C++ extensions (cross-compiling is not supported)"),
	]

	boolean_options = _build_ext.boolean_options + [
		'portage-ext-modules',
	]

	def initialize_options(self):
		_build_ext.initialize_options(self)
		self.portage_ext_modules = None

	def run(self):
		if self.portage_ext_modules:
			_build_ext.run(self)


setup(
	name = 'portage',
	version = '3.0.20',
	url = 'https://wiki.gentoo.org/wiki/Project:Portage',
	project_urls = {
		'Release Notes': 'https://gitweb.gentoo.org/proj/portage.git/plain/RELEASE-NOTES',
		'Documentation': 'https://wiki.gentoo.org/wiki/Handbook:AMD64/Working/Portage',
	},
	author = 'Gentoo Portage Development Team',
	author_email = 'dev-portage@gentoo.org',
	description = 'Portage is the package management and distribution system for Gentoo',
	license = 'GPLV2',
	long_description = long_description,
	long_description_content_type = 'text/plain',

	package_dir = {'': 'lib'},
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
	entry_points={
		"console_scripts": [
			"{}=portage.util.bin_entry_point:bin_entry_point".format(os.path.basename(path))
			for path in itertools.chain.from_iterable(x_scripts.values())
		],
	} if create_entry_points else {},
	# create_entry_points disables ext_modules, for pure python
	ext_modules = [] if create_entry_points else [
		Extension(name=n, sources=m,
		extra_compile_args=['-D_FILE_OFFSET_BITS=64',
		'-D_LARGEFILE_SOURCE', '-D_LARGEFILE64_SOURCE'])
		for n, m in x_c_helpers.items()],

	cmdclass = {
		'build': x_build,
		'build_ext': build_ext,
		'build_man': build_man,
		'build_scripts': x_build_scripts,
		'build_scripts_bin': x_build_scripts_bin,
		'build_scripts_portagebin': x_build_scripts_portagebin,
		'build_scripts_sbin': x_build_scripts_sbin,
		'build_tests': build_tests,
		'clean': x_clean,
		'docbook': docbook,
		'apidoc': apidoc,
		'install': x_install,
		'install_data': x_install_data,
		'install_docbook': install_docbook,
		'install_apidoc': install_apidoc,
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
		'Programming Language :: Python :: 3',
		'Topic :: System :: Installation/Setup'
	],

	python_requires = ">=3.6",
)
