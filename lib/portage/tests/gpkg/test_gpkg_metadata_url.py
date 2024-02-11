# Copyright 2022-2024 Gentoo Authors
# Portage Unit Testing Functionality

import io
import tarfile
import tempfile
from functools import partial
from os import urandom
from concurrent.futures import Future

from portage.gpkg import gpkg
from portage import os
from portage import shutil
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.exception import InvalidSignature
from portage.gpg import GPG


class test_gpkg_metadata_url_case(TestCase):
    def httpd(self, directory, httpd_future):
        try:
            import http.server
            import socketserver
        except ImportError:
            self.skipTest("http server not exits")

        Handler = partial(http.server.SimpleHTTPRequestHandler, directory=directory)

        with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
            httpd_future.set_result(httpd)
            httpd.serve_forever()

    def start_http_server(self, directory):
        try:
            import threading
        except ImportError:
            self.skipTest("threading module not exists")

        httpd_future = Future()
        server = threading.Thread(
            target=self.httpd, args=(directory, httpd_future), daemon=True
        )
        server.start()
        return httpd_future.result()

    def test_gpkg_get_metadata_url(self):
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
        server = None
        try:
            settings = playground.settings
            server = self.start_http_server(tmpdir)

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
                "http://{}:{}/test.gpkg.tar".format(*server.server_address)
            )

            self.assertEqual(meta, meta_from_url)
        finally:
            if server is not None:
                server.shutdown()
            shutil.rmtree(tmpdir)
            playground.cleanup()

    def test_gpkg_get_metadata_url_unknown_signature(self):
        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'BINPKG_COMPRESS="gzip"',
                    'FEATURES="${FEATURES} binpkg-signing ' 'binpkg-request-signature"',
                ),
            }
        )
        tmpdir = tempfile.mkdtemp()
        gpg = None
        server = None
        try:
            settings = playground.settings
            gpg = GPG(settings)
            gpg.unlock()

            server = self.start_http_server(tmpdir)

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
                "http://{}:{}/test-2.gpkg.tar".format(*server.server_address),
            )
        finally:
            if gpg is not None:
                gpg.stop()
            if server is not None:
                server.shutdown()
            shutil.rmtree(tmpdir)
            playground.cleanup()
