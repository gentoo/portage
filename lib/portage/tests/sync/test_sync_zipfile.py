# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import http.server
import os
import shutil
import socketserver
import subprocess
import tempfile
import textwrap
import threading
from functools import partial

import portage
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class test_sync_zipfile_case(TestCase):
    def test_sync_zipfile(self):
        cpv = "dev-libs/A-0"
        ebuilds = {
            cpv: {"EAPI": "8"},
        }
        etag = "foo"

        server = None
        playground = None
        tmpdir = tempfile.mkdtemp()
        try:

            class Handler(http.server.SimpleHTTPRequestHandler):
                def end_headers(self):
                    self.send_header("etag", etag)
                    super().end_headers()

            server = socketserver.TCPServer(
                ("127.0.0.1", 0),
                partial(Handler, directory=tmpdir),
            )
            threading.Thread(target=server.serve_forever, daemon=True).start()

            playground = ResolverPlayground(
                ebuilds=ebuilds,
            )
            settings = playground.settings

            env = settings.environ()

            repos_conf = textwrap.dedent(
                """
                [test_repo]
                location = %(location)s
                sync-type = zipfile
                sync-uri = %(sync-uri)s
                auto-sync = true
            """
            )

            repo_location = f"{playground.eprefix}/var/repositories/test_repo"

            env["PORTAGE_REPOSITORIES"] = repos_conf % {
                "location": repo_location,
                "sync-uri": "http://{}:{}/test_repo.zip".format(*server.server_address),
            }

            shutil.make_archive(os.path.join(tmpdir, "test_repo"), "zip", repo_location)

            ebuild = playground.trees[playground.eroot]["porttree"].dbapi.findname(cpv)
            self.assertTrue(os.path.exists(ebuild))
            shutil.rmtree(repo_location)
            self.assertFalse(os.path.exists(ebuild))

            result = subprocess.run(
                [
                    "emerge",
                    "--sync",
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            output = result.stdout.decode(errors="replace")
            try:
                self.assertEqual(result.returncode, os.EX_OK)
            except Exception:
                print(output)
                raise

            repo = settings.repositories["test_repo"]
            sync_mod = portage.sync.module_controller.get_class("zipfile")
            status, repo_revision = sync_mod().retrieve_head(options={"repo": repo})
            self.assertEqual(status, os.EX_OK)
            self.assertEqual(repo_revision, etag)
        finally:
            if server is not None:
                server.shutdown()
            shutil.rmtree(tmpdir)
            playground.cleanup()
