# Copyright 2019-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools
import shutil
import socket
import struct
import tempfile
import time

import portage
from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util import socks5
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

	def __enter__(self):
		httpd = self._httpd = HTTPServer((self._host, 0), functools.partial(_Handler, self._content))
		self.server_port = httpd.server_port
		self._loop.add_reader(httpd.socket.fileno(), self._httpd._handle_request_noblock)
		return self

	def __exit__(self, exc_type, exc_value, exc_traceback):
		if self._httpd is not None:
			self._loop.remove_reader(self._httpd.socket.fileno())
			self._httpd.socket.close()
			self._httpd = None


class AsyncHTTPServerTestCase(TestCase):

	@staticmethod
	def _fetch_directly(host, port, path):
		# NOTE: python2.7 does not have context manager support here
		try:
			f = urlopen('http://{host}:{port}{path}'.format( # nosec
				host=host, port=port, path=path))
			return f.read()
		finally:
			if f is not None:
				f.close()

	def test_http_server(self):
		host = '127.0.0.1'
		content = b'Hello World!\n'
		path = '/index.html'
		loop = global_event_loop()
		for i in range(2):
			with AsyncHTTPServer(host, {path: content}, loop) as server:
				for j in range(2):
					result = loop.run_until_complete(loop.run_in_executor(None,
						self._fetch_directly, host, server.server_port, path))
					self.assertEqual(result, content)


class _socket_file_wrapper(portage.proxy.objectproxy.ObjectProxy):
	"""
	A file-like object that wraps a socket and closes the socket when
	closed. Since python2.7 does not support socket.detach(), this is a
	convenient way to have a file attached to a socket that closes
	automatically (without resource warnings about unclosed sockets).
	"""

	__slots__ = ('_file', '_socket')

	def __init__(self, socket, f):
		object.__setattr__(self, '_socket', socket)
		object.__setattr__(self, '_file', f)

	def _get_target(self):
		return object.__getattribute__(self, '_file')

	def __getattribute__(self, attr):
		if attr == 'close':
			return object.__getattribute__(self, 'close')
		return super(_socket_file_wrapper, self).__getattribute__(attr)

	def __enter__(self):
		return self

	def close(self):
		object.__getattribute__(self, '_file').close()
		object.__getattribute__(self, '_socket').close()

	def __exit__(self, exc_type, exc_value, traceback):
		self.close()


def socks5_http_get_ipv4(proxy, host, port, path):
	"""
	Open http GET request via socks5 proxy listening on a unix socket,
	and return a file to read the response body from.
	"""
	s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
	f = _socket_file_wrapper(s, s.makefile('rb', 1024))
	try:
		s.connect(proxy)
		s.send(struct.pack('!BBB', 0x05, 0x01, 0x00))
		vers, method = struct.unpack('!BB', s.recv(2))
		s.send(struct.pack('!BBBB', 0x05, 0x01, 0x00, 0x01))
		s.send(socket.inet_pton(socket.AF_INET, host))
		s.send(struct.pack('!H', port))
		reply = struct.unpack('!BBB', s.recv(3))
		if reply != (0x05, 0x00, 0x00):
			raise AssertionError(repr(reply))
		struct.unpack('!B4sH', s.recv(7)) # contains proxied address info
		s.send("GET {} HTTP/1.1\r\nHost: {}:{}\r\nAccept: */*\r\nConnection: close\r\n\r\n".format(
			path, host, port).encode())
		headers = []
		while True:
			headers.append(f.readline())
			if headers[-1] == b'\r\n':
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

		loop = global_event_loop()

		host = '127.0.0.1'
		content = b'Hello World!'
		path = '/index.html'
		proxy = None
		tempdir = tempfile.mkdtemp()

		try:
			with AsyncHTTPServer(host, {path: content}, loop) as server:

				settings = {
					'PORTAGE_TMPDIR': tempdir,
					'PORTAGE_BIN_PATH': PORTAGE_BIN_PATH,
				}

				proxy = socks5.get_socks5_proxy(settings)
				loop.run_until_complete(socks5.proxy.ready())

				result = loop.run_until_complete(loop.run_in_executor(None,
					self._fetch_via_proxy, proxy, host, server.server_port, path))

				self.assertEqual(result, content)
		finally:
			socks5.proxy.stop()
			shutil.rmtree(tempdir)
