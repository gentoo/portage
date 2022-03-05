# Copyright 2006-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io
import json
import tempfile
from unittest import mock

from portage import os
from portage.tests import TestCase
from portage.util import mtimedb

class TestMtimeDB(TestCase):

    def testMtimeLastUpdateMissing(self):
        with mock.patch('builtins.open', return_value=io.StringIO()):
            db = mtimedb.MtimeDB('/none')
            self.assertEqual(db.lastUpdated(), -1)

    def testMtimeLastUpdatePresent(self):
        d = { mtimedb.MtimeDB._LAST_UPDATED_KEY: 12345 }
        output = io.StringIO()
        json.dump(d, output)
        output.seek(0) # Seek to start of io so mtime gets the content.
        with mock.patch('builtins.open', return_value=output):
            db = mtimedb.MtimeDB('/none')
            self.assertEqual(db.lastUpdated(), 12345)

    def testCommitUpdatesLastUpdatedTime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpfile = os.path.join(tmpdir, 'mtimedb')
            json.dump({}, open(tmpfile, 'w'))
            db = mtimedb.MtimeDB(tmpfile)
            # db.commit will not update unless there are pending diffs, so force one.
            db['version'] = 'foo'
            db.commit()
            db._load(tmpfile)
            self.assertNotEqual(db.lastUpdated(), -1)