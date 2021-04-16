# Copyright 2020-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import argparse
import os
import shutil
import tempfile
import time

from portage.tests import TestCase
from portage.util.shelve import dump, open_shelve, restore


class ShelveUtilsTestCase(TestCase):

	TEST_DATA = (
		# distfiles_db
		{
			"portage-2.3.89.tar.bz2": "sys-apps/portage-2.3.89",
			"portage-2.3.99.tar.bz2": "sys-apps/portage-2.3.99",
		},
		# deletion_db
		{
			"portage-2.3.89.tar.bz2": time.time(),
			"portage-2.3.99.tar.bz2": time.time(),
		},
		# recycle_db
		{
			"portage-2.3.89.tar.bz2": (0, time.time()),
			"portage-2.3.99.tar.bz2": (0, time.time()),
		},
	)

	def test_dump_restore(self):
		for data in self.TEST_DATA:
			tmpdir = tempfile.mkdtemp()
			try:
				dump_args = argparse.Namespace(
					src=os.path.join(tmpdir, "shelve_file"),
					dest=os.path.join(tmpdir, "pickle_file"),
				)
				db = open_shelve(dump_args.src, flag="c")
				for k, v in data.items():
					db[k] = v
				db.close()
				dump(dump_args)

				os.unlink(dump_args.src)
				restore_args = argparse.Namespace(
					dest=dump_args.src,
					src=dump_args.dest,
				)
				restore(restore_args)

				db = open_shelve(restore_args.dest, flag="r")
				for k, v in data.items():
					self.assertEqual(db[k], v)
				db.close()
			finally:
				shutil.rmtree(tmpdir)
