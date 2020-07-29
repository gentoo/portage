# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'AbstractEventLoopPolicy',
	'AbstractEventLoop',
)

import socket
import subprocess

from asyncio.events import (
	AbstractEventLoop as _AbstractEventLoop,
	AbstractEventLoopPolicy as _AbstractEventLoopPolicy,
)


class AbstractEventLoopPolicy(_AbstractEventLoopPolicy):
	"""Abstract policy for accessing the event loop."""

	def get_event_loop(self):
		raise NotImplementedError

	def set_event_loop(self, loop):
		raise NotImplementedError

	def new_event_loop(self):
		raise NotImplementedError

	def get_child_watcher(self):
		raise NotImplementedError

	def set_child_watcher(self, watcher):
		raise NotImplementedError


class AbstractEventLoop(_AbstractEventLoop):
	"""Abstract event loop."""

	def run_forever(self):
		raise NotImplementedError

	def run_until_complete(self, future):
		raise NotImplementedError

	def stop(self):
		raise NotImplementedError

	def is_running(self):
		raise NotImplementedError

	def is_closed(self):
		raise NotImplementedError

	def close(self):
		raise NotImplementedError

	def shutdown_asyncgens(self):
		raise NotImplementedError

	def _timer_handle_cancelled(self, handle):
		raise NotImplementedError

	def call_soon(self, callback, *args):
		return self.call_later(0, callback, *args)

	def call_later(self, delay, callback, *args):
		raise NotImplementedError

	def call_at(self, when, callback, *args):
		raise NotImplementedError

	def time(self):
		raise NotImplementedError

	def create_future(self):
		raise NotImplementedError

	def create_task(self, coro):
		raise NotImplementedError

	def call_soon_threadsafe(self, callback, *args):
		raise NotImplementedError

	def run_in_executor(self, executor, func, *args):
		raise NotImplementedError

	def set_default_executor(self, executor):
		raise NotImplementedError

	def getaddrinfo(self, host, port, family=0, type=0, proto=0, flags=0): # pylint: disable=redefined-builtin
		raise NotImplementedError

	def getnameinfo(self, sockaddr, flags=0):
		raise NotImplementedError

	def create_connection(self, protocol_factory, host=None, port=None,
						  ssl=None, family=0, proto=0, flags=0, sock=None,
						  local_addr=None, server_hostname=None):
		raise NotImplementedError

	def create_server(self, protocol_factory, host=None, port=None,
					  family=socket.AF_UNSPEC, flags=socket.AI_PASSIVE,
					  sock=None, backlog=100, ssl=None, reuse_address=None,
					  reuse_port=None):
		raise NotImplementedError

	def create_unix_connection(self, protocol_factory, path,
							   ssl=None, sock=None,
							   server_hostname=None):
		raise NotImplementedError

	def create_unix_server(self, protocol_factory, path,
						   sock=None, backlog=100, ssl=None):
		raise NotImplementedError

	def create_datagram_endpoint(self, protocol_factory,
								 local_addr=None, remote_addr=None,
								 family=0, proto=0, flags=0,
								 reuse_address=None, reuse_port=None,
								 allow_broadcast=None, sock=None):
		raise NotImplementedError

	def connect_read_pipe(self, protocol_factory, pipe):
		raise NotImplementedError

	def connect_write_pipe(self, protocol_factory, pipe):
		raise NotImplementedError

	def subprocess_shell(self, protocol_factory, cmd, stdin=subprocess.PIPE,
						 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
						 **kwargs):
		raise NotImplementedError

	def subprocess_exec(self, protocol_factory, *args, **kwargs):
		for k in ('stdin', 'stdout', 'stderr'):
			kwargs.setdefault(k, subprocess.PIPE)
		raise NotImplementedError

	def add_writer(self, fd, callback, *args):
		raise NotImplementedError

	def remove_writer(self, fd):
		raise NotImplementedError

	def sock_recv(self, sock, nbytes):
		raise NotImplementedError

	def sock_sendall(self, sock, data):
		raise NotImplementedError

	def sock_connect(self, sock, address):
		raise NotImplementedError

	def sock_accept(self, sock):
		raise NotImplementedError

	def add_signal_handler(self, sig, callback, *args):
		raise NotImplementedError

	def remove_signal_handler(self, sig):
		raise NotImplementedError

	def set_task_factory(self, factory):
		raise NotImplementedError

	def get_task_factory(self):
		raise NotImplementedError

	def get_exception_handler(self):
		raise NotImplementedError

	def set_exception_handler(self, handler):
		raise NotImplementedError

	def default_exception_handler(self, context):
		raise NotImplementedError

	def call_exception_handler(self, context):
		raise NotImplementedError

	def get_debug(self):
		raise NotImplementedError

	def set_debug(self, enabled):
		raise NotImplementedError
