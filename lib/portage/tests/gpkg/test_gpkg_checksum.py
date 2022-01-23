# Copright Gentoo Foundation 2006-2020
# Portage Unit Testing Functionality

import io
import sys
import tarfile
import tempfile
from os import urandom

from portage import os
from portage import shutil
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.gpkg import gpkg
from portage.exception import (
    InvalidBinaryPackageFormat,
    DigestException,
    MissingSignature,
)


class test_gpkg_checksum_case(TestCase):
    def test_gpkg_missing_header(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} -binpkg-signing '
                    '-binpkg-request-signature -gpg-keepalive"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if f.name != binpkg_1.gpkg_version:
                            tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))

            self.assertRaises(
                InvalidBinaryPackageFormat,
                binpkg_2.decompress,
                os.path.join(tmpdir, "test"),
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_missing_manifest(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} -binpkg-signing '
                    '-binpkg-request-signature -gpg-keepalive"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if f.name != "Manifest":
                            tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))

            self.assertRaises(
                MissingSignature, binpkg_2.decompress, os.path.join(tmpdir, "test")
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_missing_files(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} -binpkg-signing '
                    '-binpkg-request-signature -gpg-keepalive"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data2"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if "image.tar" not in f.name:
                            tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))

            self.assertRaises(
                DigestException, binpkg_2.decompress, os.path.join(tmpdir, "test")
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_extra_files(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} -binpkg-signing '
                    '-binpkg-request-signature -gpg-keepalive"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        tar_2.addfile(f, tar_1.extractfile(f))
                    data_tarinfo = tarfile.TarInfo("data2")
                    data_tarinfo.size = len(data)
                    data2 = io.BytesIO(data)
                    tar_2.addfile(data_tarinfo, data2)
                    data2.close()

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))

            self.assertRaises(
                DigestException, binpkg_2.decompress, os.path.join(tmpdir, "test")
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_incorrect_checksum(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} -binpkg-signing '
                    '-binpkg-request-signature -gpg-keepalive"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(1048576)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if f.name == "Manifest":
                            data = io.BytesIO(tar_1.extractfile(f).read())
                            data_view = data.getbuffer()
                            data_view[-16:] = b"20a6d80ab0320fh9"
                            del data_view
                            tar_2.addfile(f, data)
                            data.close()
                        else:
                            tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))

            self.assertRaises(
                DigestException, binpkg_2.decompress, os.path.join(tmpdir, "test")
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_duplicate_files(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} -binpkg-signing '
                    '-binpkg-request-signature -gpg-keepalive"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(100)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        tar_2.addfile(f, tar_1.extractfile(f))
                        tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))

            self.assertRaises(
                InvalidBinaryPackageFormat,
                binpkg_2.decompress,
                os.path.join(tmpdir, "test"),
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_manifest_duplicate_files(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} -binpkg-signing '
                    '-binpkg-request-signature -gpg-keepalive"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(100)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if f.name == "Manifest":
                            manifest = tar_1.extractfile(f).read()
                            data = io.BytesIO(manifest)
                            data.seek(io.SEEK_END)
                            data.write(b"\n")
                            data.write(manifest)
                            f.size = data.tell()
                            data.seek(0)
                            tar_2.addfile(f, data)
                            data.close()
                        else:
                            tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))

            self.assertRaises(
                DigestException, binpkg_2.decompress, os.path.join(tmpdir, "test")
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_different_size_file(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} -binpkg-signing '
                    '-binpkg-request-signature -gpg-keepalive"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()

        try:
            settings = playground.settings
            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            data = urandom(100)
            with open(os.path.join(orig_full_path, "data"), "wb") as f:
                f.write(data)

            binpkg_1 = gpkg(settings, "test", os.path.join(tmpdir, "test-1.gpkg.tar"))
            binpkg_1.compress(orig_full_path, {})

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        tar_2.addfile(f, tar_1.extractfile(f))
                        tar_2.addfile(f, tar_1.extractfile(f))

            binpkg_2 = gpkg(settings, "test", os.path.join(tmpdir, "test-2.gpkg.tar"))

            self.assertRaises(
                InvalidBinaryPackageFormat,
                binpkg_2.decompress,
                os.path.join(tmpdir, "test"),
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()
