# Copyright 2019-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import asyncio
import functools
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time

import portage
from portage.tests import TestCase, get_pythonpath
from portage.util import socks5
from portage.util.futures.executor.fork import ForkExecutor
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.const import PORTAGE_BIN_PATH

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import urlopen


class _Handler(BaseHTTPRequestHandler):
    def __init__(self, content, *args, **kwargs):
        self.content = content
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def do_GET(self):
        doc = self.send_head()
        if doc is not None:
            self.wfile.write(doc)

    def do_HEAD(self):
        self.send_head()

    def send_head(self):
        doc = self.content.get(self.path)
        if doc is None:
            self.send_error(404, "File not found")
            return None

        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.send_header("Content-Length", len(doc))
        self.send_header("Last-Modified", self.date_time_string(time.time()))
        self.end_headers()
        return doc

    def log_message(self, fmt, *args):
        pass


class AsyncHTTPServer:
    def __init__(self, host, content, loop):
        self._host = host
        self._content = content
        self._loop = loop
        self.server_port = None
        self._httpd = None

    def pause(self):
        """Pause responses (useful for testing timeouts)."""
        self._loop.remove_reader(self._httpd.socket.fileno())

    def resume(self):
        """Resume responses following a previous call to pause."""
        self._loop.add_reader(
            self._httpd.socket.fileno(), self._httpd._handle_request_noblock
        )

    def __enter__(self):
        httpd = self._httpd = HTTPServer(
            (self._host, 0), functools.partial(_Handler, self._content)
        )
        self.server_port = httpd.server_port
        self.resume()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self._httpd is not None:
            self.pause()
            self._httpd.socket.close()
            self._httpd = None


class AsyncHTTPServerTestCase(TestCase):
    @staticmethod
    def _fetch_directly(host, port, path):
        # NOTE: python2.7 does not have context manager support here
        try:
            f = urlopen(
                "http://{host}:{port}{path}".format(  # nosec
                    host=host, port=port, path=path
                )
            )
            return f.read()
        finally:
            if f is not None:
                f.close()

    async def _test_http_server(self):
        asyncio.run(self._test_http_server())

    async def _test_http_server(self):
        host = "127.0.0.1"
        content = b"Hello World!\n"
        path = "/index.html"

        loop = asyncio.get_running_loop()
        for i in range(2):
            with AsyncHTTPServer(host, {path: content}, loop) as server:
                for j in range(2):
                    result = await loop.run_in_executor(
                        None, self._fetch_directly, host, server.server_port, path
                    )
                    self.assertEqual(result, content)


class _socket_file_wrapper(portage.proxy.objectproxy.ObjectProxy):
    """
    A file-like object that wraps a socket and closes the socket when
    closed. Since python2.7 does not support socket.detach(), this is a
    convenient way to have a file attached to a socket that closes
    automatically (without resource warnings about unclosed sockets).
    """

    __slots__ = ("_file", "_socket")

    def __init__(self, socket, f):
        object.__setattr__(self, "_socket", socket)
        object.__setattr__(self, "_file", f)

    def _get_target(self):
        return object.__getattribute__(self, "_file")

    def __getattribute__(self, attr):
        if attr == "close":
            return object.__getattribute__(self, "close")
        return super().__getattribute__(attr)

    def __enter__(self):
        return self

    def close(self):
        object.__getattribute__(self, "_file").close()
        object.__getattribute__(self, "_socket").close()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def socks5_http_get_ipv4(proxy, host, port, path):
    """
    Open http GET request via socks5 proxy listening on a unix socket,
    and return a file to read the response body from.
    """
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    f = _socket_file_wrapper(s, s.makefile("rb", 1024))
    try:
        s.connect(proxy)
        s.send(struct.pack("!BBB", 0x05, 0x01, 0x00))
        vers, method = struct.unpack("!BB", s.recv(2))
        s.send(struct.pack("!BBBB", 0x05, 0x01, 0x00, 0x01))
        s.send(socket.inet_pton(socket.AF_INET, host))
        s.send(struct.pack("!H", port))
        reply = struct.unpack("!BBB", s.recv(3))
        if reply != (0x05, 0x00, 0x00):
            raise AssertionError(repr(reply))
        struct.unpack("!B4sH", s.recv(7))  # contains proxied address info
        s.send(
            "GET {} HTTP/1.1\r\nHost: {}:{}\r\nAccept: */*\r\nConnection: close\r\n\r\n".format(
                path, host, port
            ).encode()
        )
        headers = []
        while True:
            headers.append(f.readline())
            if headers[-1] == b"\r\n":
                return f
    except Exception:
        f.close()
        raise


class Socks5ServerTestCase(TestCase):
    @staticmethod
    def _fetch_via_proxy(proxy, host, port, path):
        with socks5_http_get_ipv4(proxy, host, port, path) as f:
            return f.read()

    def test_socks5_proxy(self):
        asyncio.run(self._test_socks5_proxy())

    async def _test_socks5_proxy(self):
        loop = global_event_loop()

        host = "127.0.0.1"
        content = b"Hello World!"
        path = "/index.html"
        proxy = None
        tempdir = tempfile.mkdtemp()
        previous_exithandlers = loop._coroutine_exithandlers

        try:
            loop._coroutine_exithandlers = []
            with AsyncHTTPServer(host, {path: content}, loop) as server:
                settings = {
                    "PORTAGE_TMPDIR": tempdir,
                    "PORTAGE_BIN_PATH": PORTAGE_BIN_PATH,
                }

                proxy = socks5.get_socks5_proxy(settings)
                await socks5.proxy.ready()

                result = await loop.run_in_executor(
                    None,
                    self._fetch_via_proxy,
                    proxy,
                    host,
                    server.server_port,
                    path,
                )

                self.assertEqual(result, content)
        finally:
            try:
                # Also run_coroutine_exitfuncs to test atexit hook cleanup.
                self.assertNotEqual(loop._coroutine_exithandlers, [])
                await portage.process.run_coroutine_exitfuncs()
                self.assertEqual(loop._coroutine_exithandlers, [])
            finally:
                loop._coroutine_exithandlers = previous_exithandlers
                shutil.rmtree(tempdir)


class Socks5ServerLoopCloseTestCase(TestCase):
    """
    For bug 925240, test that the socks5 proxy is automatically
    terminated when the main event loop is closed, using a subprocess
    for isolation.
    """

    def testSocks5ServerLoopClose(self):
        asyncio.run(self._testSocks5ServerLoopClose())

    async def _testSocks5ServerLoopClose(self):
        loop = asyncio.get_running_loop()
        self.assertEqual(
            await loop.run_in_executor(
                ForkExecutor(loop=loop), self._testSocks5ServerLoopCloseSubprocess
            ),
            True,
        )

    @staticmethod
    def _testSocks5ServerLoopCloseSubprocess():
        loop = global_event_loop()
        tempdir = tempfile.mkdtemp()
        try:
            settings = {
                "PORTAGE_TMPDIR": tempdir,
                "PORTAGE_BIN_PATH": PORTAGE_BIN_PATH,
            }

            socks5.get_socks5_proxy(settings)
            loop.run_until_complete(socks5.proxy.ready())
        finally:
            loop.close()
            shutil.rmtree(tempdir)

        return not socks5.proxy.is_running()


class Socks5ServerAtExitTestCase(TestCase):
    """
    For bug 937384, test that the socks5 proxy is automatically
    terminated by portage.process.run_exitfuncs(), using a subprocess
    for isolation.

    Note that if the subprocess is created via fork then it will be
    vulnerable to python issue 83856 which is only fixed in python3.13,
    so this test uses python -c to ensure that atexit hooks will work.
    """

    _threaded = False

    def testSocks5ServerAtExit(self):
        tempdir = tempfile.mkdtemp()
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = get_pythonpath()
            output = subprocess.check_output(
                [
                    portage._python_interpreter,
                    "-c",
                    """
import sys
import threading

from portage.const import PORTAGE_BIN_PATH
from portage.util import socks5
from portage.util._eventloop.global_event_loop import global_event_loop

tempdir = sys.argv[0]
threaded = bool(sys.argv[1])

settings = {
    "PORTAGE_TMPDIR": tempdir,
    "PORTAGE_BIN_PATH": PORTAGE_BIN_PATH,
}

def main():
    loop = global_event_loop()
    socks5.get_socks5_proxy(settings)
    loop.run_until_complete(socks5.proxy.ready())
    print(socks5.proxy._proc.pid, flush=True)

if __name__ == "__main__":
    if threaded:
        t = threading.Thread(target=main)
        t.start()
        t.join()
    else:
        main()
""",
                    tempdir,
                    str(self._threaded),
                ],
                env=env,
            )

            pid = int(output.strip())

            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
        finally:
            shutil.rmtree(tempdir)


class Socks5ServerAtExitThreadedTestCase(Socks5ServerAtExitTestCase):
    _threaded = True
