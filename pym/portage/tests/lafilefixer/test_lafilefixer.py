# test_lafilefixer.py -- Portage Unit Testing Functionality
# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.exception import InvalidData

class test_lafilefixer(TestCase):

	def get_test_cases_clean(self):
		yield "dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' -lm'\n" + \
			"current=6\n" + \
			"age=0\n" + \
			"revision=2\n" + \
			"installed=yes\n" + \
			"dlopen=''\n" + \
			"dlpreopen=''\n" + \
			"libdir='/usr/lib64'\n"
		yield "dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' -lm'\n" + \
			"current=6\n" + \
			"age=0\n" + \
			"revision=2\n" + \
			"installed=yes\n" + \
			"dlopen=''\n" + \
			"dlpreopen=''\n" + \
			"libdir='/usr/lib64'\n"
		yield "dependency_libs=' liba.la /usr/lib64/bar.la -lc'\n"

	def get_test_cases_update(self):
		#.la -> -l*
		yield "dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc'\n", \
			"dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' -L/usr/lib64 -la -lb -lc'\n"
		#move stuff into inherited_linker_flags
		yield "dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' /usr/lib64/liba.la -pthread /usr/lib64/libb.la -lc'\n" + \
			"inherited_linker_flags=''\n", \
			"dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' -L/usr/lib64 -la -lb -lc'\n" + \
			"inherited_linker_flags=' -pthread'\n"
		#reorder 
		yield "dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' /usr/lib64/liba.la -R/usr/lib64 /usr/lib64/libb.la -lc'\n", \
			"dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' -R/usr/lib64 -L/usr/lib64 -la -lb -lc'\n"
		#remove duplicates from dependency_libs (the original version didn't do it for inherited_linker_flags)
		yield "dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libc.la -pthread -mt" + \
			" -L/usr/lib -R/usr/lib64 -lc /usr/lib64/libb.la -lc'\n" +\
			"inherited_linker_flags=' -pthread -pthread'\n", \
			"dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' -R/usr/lib64 -L/usr/lib64 -L/usr/lib -la -lc -lb'\n" +\
			"inherited_linker_flags=' -pthread -pthread -mt'\n"
		#-L rewriting
		yield "dependency_libs=' -L/usr/X11R6/lib'\n", \
			"dependency_libs=' -L/usr/lib'\n"
		yield "dependency_libs=' -L/usr/local/lib'\n", \
			"dependency_libs=' -L/usr/lib'\n"
		yield "dependency_libs=' -L/usr/lib64/pkgconfig/../..'\n", \
			"dependency_libs=' -L/usr'\n"
		yield "dependency_libs=' -L/usr/lib/pkgconfig/..'\n", \
			"dependency_libs=' -L/usr/lib'\n"
		yield "dependency_libs=' -L/usr/lib/pkgconfig/../.. -L/usr/lib/pkgconfig/..'\n", \
			"dependency_libs=' -L/usr -L/usr/lib'\n"

	def get_test_cases_broken(self):
		yield ""
		#no dependency_libs
		yield "dlname='libfoo.so.1'\n" + \
			"current=6\n" + \
			"age=0\n" + \
			"revision=2\n"
		#borken dependency_libs
		yield "dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc' \n"
			#borken dependency_libs
		yield "dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc\n"
		#crap in dependency_libs
		yield "dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc /-lstdc++'\n"
		#dependency_libs twice
		yield "dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc /-lstdc++'\n" +\
			"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc /-lstdc++'\n"
		#inherited_linker_flags twice
		yield "dlname='libfoo.so.1'\n" + \
			"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			"old_library='libpdf.a'\n" + \
			"inherited_linker_flags=''\n" +\
			"inherited_linker_flags=''\n"

	def testlafilefixer(self):
		from portage.util.lafilefixer import _parse_lafile_contents, rewrite_lafile

		for clean_contents in self.get_test_cases_clean():
			self.assertEqual(rewrite_lafile(clean_contents), (False, None))

		for original_contents, fixed_contents in self.get_test_cases_update():
			self.assertEqual(rewrite_lafile(original_contents), (True, fixed_contents))

		for broken_contents in self.get_test_cases_broken():
			self.assertRaises(InvalidData, rewrite_lafile, broken_contents)
