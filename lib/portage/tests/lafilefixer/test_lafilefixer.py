# test_lafilefixer.py -- Portage Unit Testing Functionality
# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.exception import InvalidData

class test_lafilefixer(TestCase):

	def get_test_cases_clean(self):
		yield b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' -lm'\n" + \
			b"current=6\n" + \
			b"age=0\n" + \
			b"revision=2\n" + \
			b"installed=yes\n" + \
			b"dlopen=''\n" + \
			b"dlpreopen=''\n" + \
			b"libdir='/usr/lib64'\n"
		yield b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' -lm'\n" + \
			b"current=6\n" + \
			b"age=0\n" + \
			b"revision=2\n" + \
			b"installed=yes\n" + \
			b"dlopen=''\n" + \
			b"dlpreopen=''\n" + \
			b"libdir='/usr/lib64'\n"
		yield b"dependency_libs=' liba.la /usr/lib64/bar.la -lc'\n"

	def get_test_cases_update(self):
		#.la -> -l*
		yield b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc'\n", \
			b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' -L/usr/lib64 -la -lb -lc'\n"
		#move stuff into inherited_linker_flags
		yield b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' /usr/lib64/liba.la -pthread /usr/lib64/libb.la -lc'\n" + \
			b"inherited_linker_flags=''\n", \
			b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' -L/usr/lib64 -la -lb -lc'\n" + \
			b"inherited_linker_flags=' -pthread'\n"
		#reorder
		yield b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' /usr/lib64/liba.la -R/usr/lib64 /usr/lib64/libb.la -lc'\n", \
			b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' -R/usr/lib64 -L/usr/lib64 -la -lb -lc'\n"
		#remove duplicates from dependency_libs (the original version didn't do it for inherited_linker_flags)
		yield b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libc.la -pthread -mt" + \
			b" -L/usr/lib -R/usr/lib64 -lc /usr/lib64/libb.la -lc'\n" +\
			b"inherited_linker_flags=' -pthread -pthread'\n", \
			b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' -R/usr/lib64 -L/usr/lib64 -L/usr/lib -la -lc -lb'\n" +\
			b"inherited_linker_flags=' -pthread -pthread -mt'\n"
		#-L rewriting
		yield b"dependency_libs=' -L/usr/X11R6/lib'\n", \
			b"dependency_libs=' -L/usr/lib'\n"
		yield b"dependency_libs=' -L/usr/local/lib'\n", \
			b"dependency_libs=' -L/usr/lib'\n"
		yield b"dependency_libs=' -L/usr/lib64/pkgconfig/../..'\n", \
			b"dependency_libs=' -L/usr'\n"
		yield b"dependency_libs=' -L/usr/lib/pkgconfig/..'\n", \
			b"dependency_libs=' -L/usr/lib'\n"
		yield b"dependency_libs=' -L/usr/lib/pkgconfig/../.. -L/usr/lib/pkgconfig/..'\n", \
			b"dependency_libs=' -L/usr -L/usr/lib'\n"
		#we once got a backtrace on this one
		yield b"dependency_libs=' /usr/lib64/libMagickCore.la -L/usr/lib64 -llcms2 /usr/lib64/libtiff.la " + \
			b"-ljbig -lc /usr/lib64/libfreetype.la /usr/lib64/libjpeg.la /usr/lib64/libXext.la " + \
			b"/usr/lib64/libXt.la /usr/lib64/libSM.la -lICE -luuid /usr/lib64/libICE.la /usr/lib64/libX11.la " + \
			b"/usr/lib64/libxcb.la /usr/lib64/libXau.la /usr/lib64/libXdmcp.la -lbz2 -lz -lm " + \
			b"/usr/lib/gcc/x86_64-pc-linux-gnu/4.4.4/libgomp.la -lrt -lpthread /usr/lib64/libltdl.la -ldl " + \
			b"/usr/lib64/libfpx.la -lstdc++'", \
			b"dependency_libs=' -L/usr/lib64 -L/usr/lib/gcc/x86_64-pc-linux-gnu/4.4.4 -lMagickCore -llcms2 " + \
			b"-ltiff -ljbig -lc -lfreetype -ljpeg -lXext -lXt -lSM -lICE -luuid -lX11 -lxcb -lXau -lXdmcp " + \
			b"-lbz2 -lz -lm -lgomp -lrt -lpthread -lltdl -ldl -lfpx -lstdc++'"


	def get_test_cases_broken(self):
		yield b""
		#no dependency_libs
		yield b"dlname='libfoo.so.1'\n" + \
			b"current=6\n" + \
			b"age=0\n" + \
			b"revision=2\n"
		#borken dependency_libs
		yield b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc' \n"
			#borken dependency_libs
		yield b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc\n"
		#crap in dependency_libs
		yield b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc /-lstdc++'\n"
		#dependency_libs twice
		yield b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc /-lstdc++'\n" +\
			b"dependency_libs=' /usr/lib64/liba.la /usr/lib64/libb.la -lc /-lstdc++'\n"
		#inherited_linker_flags twice
		yield b"dlname='libfoo.so.1'\n" + \
			b"library_names='libfoo.so.1.0.2 libfoo.so.1 libfoo.so'\n" + \
			b"old_library='libpdf.a'\n" + \
			b"inherited_linker_flags=''\n" +\
			b"inherited_linker_flags=''\n"

	def testlafilefixer(self):
		from portage.util.lafilefixer import _parse_lafile_contents, rewrite_lafile

		for clean_contents in self.get_test_cases_clean():
			self.assertEqual(rewrite_lafile(clean_contents), (False, None))

		for original_contents, fixed_contents in self.get_test_cases_update():
			self.assertEqual(rewrite_lafile(original_contents), (True, fixed_contents))

		for broken_contents in self.get_test_cases_broken():
			self.assertRaises(InvalidData, rewrite_lafile, broken_contents)
