# Copright Gentoo Foundation 2006-2020
# Portage Unit Testing Functionality

import io
import random
import sys
import tarfile
import tempfile
from functools import partial
from os import urandom

from portage.gpkg import gpkg
from portage import os
from portage import shutil
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.exception import InvalidSignature
from portage.gpg import GPG


class test_gpkg_metadata_url_case(TestCase):
    def httpd(self, directory, port):
        try:
            import http.server
            import socketserver
        except ImportError:
            self.skipTest("http server not exits")

        Handler = partial(http.server.SimpleHTTPRequestHandler, directory=directory)

        with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
            httpd.serve_forever()

    def start_http_server(self, directory, port):
        try:
            import threading
        except ImportError:
            self.skipTest("threading module not exists")

        server = threading.Thread(
            target=self.httpd, args=(directory, port), daemon=True
        )
        server.start()
        return server

    def test_gpkg_get_metadata_url(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        if sys.version_info.major == 3 and sys.version_info.minor <= 6:
            self.skipTest("http server not support change root dir")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'BINPKG_COMPRESS="gzip"',
                    'FEATURES="${FEATURES} -binpkg-signing '
                    '-binpkg-request-signature"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()
        try:
            settings = playground.settings
            for _ in range(0, 5):
                port = random.randint(30000, 60000)
                try:
                    server = self.start_http_server(tmpdir, port)
                except OSError:
                    continue
                break

            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            with open(os.path.join(orig_full_path, "test"), "wb") as test_file:
                test_file.write(urandom(1048576))

            gpkg_file_loc = os.path.join(tmpdir, "test.gpkg.tar")
            test_gpkg = gpkg(settings, "test", gpkg_file_loc)

            meta = {
                "test1": b"{abcdefghijklmnopqrstuvwxyz, 1234567890}",
                "test2": urandom(102400),
            }

            test_gpkg.compress(os.path.join(tmpdir, "orig"), meta)

            meta_from_url = test_gpkg.get_metadata_url(
                "http://127.0.0.1:" + str(port) + "/test.gpkg.tar"
            )

            self.assertEqual(meta, meta_from_url)
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_get_metadata_url_unknown_signature(self):
        if sys.version_info.major < 3:
            self.skipTest("Not support Python 2")

        if sys.version_info.major == 3 and sys.version_info.minor <= 6:
            self.skipTest("http server not support change root dir")

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'BINPKG_COMPRESS="gzip"',
                    'FEATURES="${FEATURES} binpkg-signing ' 'binpkg-request-signature"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()
        try:
            settings = playground.settings
            gpg = GPG(settings)
            gpg.unlock()

            for _ in range(0, 5):
                port = random.randint(30000, 60000)
                try:
                    server = self.start_http_server(tmpdir, port)
                except OSError:
                    continue
                break

            orig_full_path = os.path.join(tmpdir, "orig/")
            os.makedirs(orig_full_path)

            with open(os.path.join(orig_full_path, "test"), "wb") as test_file:
                test_file.write(urandom(1048576))

            gpkg_file_loc = os.path.join(tmpdir, "test-1.gpkg.tar")
            test_gpkg = gpkg(settings, "test", gpkg_file_loc)

            meta = {
                "test1": b"{abcdefghijklmnopqrstuvwxyz, 1234567890}",
                "test2": urandom(102400),
            }

            test_gpkg.compress(os.path.join(tmpdir, "orig"), meta)

            with tarfile.open(os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
                with tarfile.open(
                    os.path.join(tmpdir, "test-2.gpkg.tar"), "w"
                ) as tar_2:
                    for f in tar_1.getmembers():
                        if f.name == "test/metadata.tar.gz":
                            sig = b"""
-----BEGIN PGP SIGNATURE-----

iHUEABYIAB0WIQRVhCbPGi/rhGTq4nV+k2dcK9uyIgUCXw4ehAAKCRB+k2dcK9uy
IkCfAP49AOYjzuQPP0n5P0SGCINnAVEXN7QLQ4PurY/lt7cT2gEAq01stXjFhrz5
87Koh+ND2r5XfQsz3XeBqbb/BpmbEgo=
=sc5K
-----END PGP SIGNATURE-----
"""
                            data = io.BytesIO(sig)
                            f.size = len(sig)
                            tar_2.addfile(f, data)
                            data.close()
                        else:
                            tar_2.addfile(f, tar_1.extractfile(f))

            test_gpkg = gpkg(settings, "test")
            self.assertRaises(
                InvalidSignature,
                test_gpkg.get_metadata_url,
                "http://127.0.0.1:" + str(port) + "/test-2.gpkg.tar",
            )
        finally:
            shutil.rmtree(tmpdir)
            playground.cleanup()
