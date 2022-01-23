# Copright Gentoo Foundation 2006-2020
# Portage Unit Testing Functionality

import sys
import tempfile
import io
import tarfile
from os import urandom

import portage.gpkg
from portage import os
from portage import shutil
from portage.tests import TestCase
from portage.exception import CompressorOperationFailed


class test_gpkg_stream_case(TestCase):
    def test_gpkg_stream_reader(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        data = urandom(1048576)
        data_io = io.BytesIO(data)
        data_io.seek(0)
        with portage.gpkg.tar_stream_reader(data_io, ["cat"]) as test_reader:
            data2 = test_reader.read()
        data_io.close()
        self.assertEqual(data, data2)

    def test_gpkg_stream_reader_without_cmd(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        data = urandom(1048576)
        data_io = io.BytesIO(data)
        data_io.seek(0)
        with portage.gpkg.tar_stream_reader(data_io) as test_reader:
            data2 = test_reader.read()
        data_io.close()
        self.assertEqual(data, data2)

    def test_gpkg_stream_reader_kill(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        data = urandom(1048576)
        data_io = io.BytesIO(data)
        data_io.seek(0)
        with portage.gpkg.tar_stream_reader(data_io, ["cat"]) as test_reader:
            try:
                test_reader.kill()
            except CompressorOperationFailed:
                pass
        data_io.close()
        self.assertNotEqual(test_reader.proc.poll(), None)

    def test_gpkg_stream_reader_kill_without_cmd(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        data = urandom(1048576)
        data_io = io.BytesIO(data)
        data_io.seek(0)
        with portage.gpkg.tar_stream_reader(data_io) as test_reader:
            test_reader.kill()
        data_io.close()
        self.assertEqual(test_reader.proc, None)

    def test_gpkg_stream_writer(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        tmpdir = tempfile.mkdtemp()
        try:
            gpkg_file_loc = os.path.join(tmpdir, "test.gpkg.tar")
            data = urandom(1048576)
            with tarfile.open(gpkg_file_loc, "w") as test_tar:
                test_tarinfo = tarfile.TarInfo("test")
                with portage.gpkg.tar_stream_writer(
                    test_tarinfo, test_tar, tarfile.USTAR_FORMAT, ["cat"]
                ) as test_writer:
                    test_writer.write(data)

            with tarfile.open(gpkg_file_loc, "r") as test_tar:
                test_tarinfo = test_tar.getmember("test")
                data2 = test_tar.extractfile(test_tarinfo).read()
                self.assertEqual(data, data2)
        finally:
            shutil.rmtree(tmpdir)

    def test_gpkg_stream_writer_without_cmd(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        tmpdir = tempfile.mkdtemp()

        try:
            gpkg_file_loc = os.path.join(tmpdir, "test.gpkg.tar")
            data = urandom(1048576)
            with tarfile.open(gpkg_file_loc, "w") as test_tar:
                test_tarinfo = tarfile.TarInfo("test")
                with portage.gpkg.tar_stream_writer(
                    test_tarinfo, test_tar, tarfile.USTAR_FORMAT
                ) as test_writer:
                    test_writer.write(data)

            with tarfile.open(gpkg_file_loc, "r") as test_tar:
                test_tarinfo = test_tar.getmember("test")
                data2 = test_tar.extractfile(test_tarinfo).read()
                self.assertEqual(data, data2)
        finally:
            shutil.rmtree(tmpdir)
