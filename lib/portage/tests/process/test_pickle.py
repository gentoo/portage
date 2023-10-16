# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import pickle

from portage.tests import TestCase
from _emerge.Package import _PackageMetadataWrapperBase
from _emerge.FifoIpcDaemon import FifoIpcDaemon


class PickleTestCase(TestCase):
    def test_PackageMetadataWrapperBase(self):
        """
        Verify that instances of slot_dict_class, like
        PackageMetadataWrapperBase, are picklable for
        compatibility with the multiprocessing spawn
        start method.
        """
        obj = _PackageMetadataWrapperBase(EAPI="8")
        self.assertEqual(obj["EAPI"], "8")
        serialized = pickle.dumps(obj)
        obj_copy = pickle.loads(serialized)
        self.assertEqual(len(obj_copy), len(obj))
        self.assertEqual(obj_copy["EAPI"], obj["EAPI"])
        self.assertEqual(obj_copy, obj)

    def test_FifoIpcDaemon_files_dict(self):
        """
        Verify that FifoIpcDaemon._files_dict instances are picklable for
        compatibility with the multiprocessing spawn start method.
        """
        obj = FifoIpcDaemon._files_dict(
            (k, "test-value") for k in FifoIpcDaemon._file_names
        )
        self.assertEqual(obj["pipe_in"], "test-value")
        # Attributes of same name exist because of slot_dict_class prefix="" argument.
        self.assertEqual(obj.pipe_in, obj["pipe_in"])
        serialized = pickle.dumps(obj)
        obj_copy = pickle.loads(serialized)
        self.assertEqual(len(obj_copy), len(obj))
        self.assertEqual(obj_copy["pipe_in"], obj["pipe_in"])
        self.assertEqual(obj_copy.pipe_in, obj["pipe_in"])
        self.assertEqual(obj_copy, obj)
