# Copyright 1999-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import division

import errno
import logging
import os
import select
import signal
import sys
import time

try:
	import fcntl
except ImportError:
	#  http://bugs.jython.org/issue1074
	fcntl = None

try:
	import threading
except ImportError:
	import dummy_threading as threading

from portage.util import writemsg_level
from ..SlotObject import SlotObject
from .PollConstants import PollConstants
from .PollSelectAdapter import PollSelectAdapter

class EventLoop(object):
	"""
	An event loop, intended to be compatible with the GLib event loop.
	Call the iteration method in order to execute one iteration of the
	loop. The idle_add and timeout_add methods serve as thread-safe
	means to interact with the loop's thread.
	"""

	supports_multiprocessing = True

	# TODO: Find out why SIGCHLD signals aren't delivered during poll
	# calls, forcing us to wakeup in order to receive them.
	_sigchld_interval = 250

	class _child_callback_class(SlotObject):
		__slots__ = ("callback", "data", "pid", "source_id")

	class _idle_callback_class(SlotObject):
		__slots__ = ("args", "callback", "calling", "source_id")

	class _io_handler_class(SlotObject):
		__slots__ = ("args", "callback", "f", "source_id")

	class _timeout_handler_class(SlotObject):
		__slots__ = ("args", "function", "calling", "interval", "source_id",
			"timestamp")

	def __init__(self, main=True):
		"""
		@param main: If True then this is a singleton instance for use
			in the main thread, otherwise it is a local instance which
			can safely be use in a non-main thread (default is True, so
			that global_event_loop does not need constructor arguments)
		@type main: bool
		"""
		self._use_signal = main and fcntl is not None
		self._thread_rlock = threading.RLock()
		self._thread_condition = threading.Condition(self._thread_rlock)
		self._poll_event_queue = []
		self._poll_event_handlers = {}
		self._poll_event_handler_ids = {}
		# Increment id for each new handler.
		self._event_handler_id = 0
		self._idle_callbacks = {}
		self._timeout_handlers = {}
		self._timeout_interval = None

		self._poll_obj = None
		try:
			select.epoll
		except AttributeError:
			pass
		else:
			try:
				epoll_obj = select.epoll()
			except IOError:
				# This happens with Linux 2.4 kernels:
				# IOError: [Errno 38] Function not implemented
				pass
			else:

				# FD_CLOEXEC is enabled by default in Python >=3.4.
				if sys.hexversion < 0x3040000 and fcntl is not None:
					try:
						fcntl.FD_CLOEXEC
					except AttributeError:
						pass
					else:
						fcntl.fcntl(epoll_obj.fileno(), fcntl.F_SETFD,
							fcntl.fcntl(epoll_obj.fileno(),
								fcntl.F_GETFD) | fcntl.FD_CLOEXEC)

				self._poll_obj = _epoll_adapter(epoll_obj)
				self.IO_ERR = select.EPOLLERR
				self.IO_HUP = select.EPOLLHUP
				self.IO_IN = select.EPOLLIN
				self.IO_NVAL = 0
				self.IO_OUT = select.EPOLLOUT
				self.IO_PRI = select.EPOLLPRI

		if self._poll_obj is None:
			self._poll_obj = create_poll_instance()
			self.IO_ERR = PollConstants.POLLERR
			self.IO_HUP = PollConstants.POLLHUP
			self.IO_IN = PollConstants.POLLIN
			self.IO_NVAL = PollConstants.POLLNVAL
			self.IO_OUT = PollConstants.POLLOUT
			self.IO_PRI = PollConstants.POLLPRI

		self._child_handlers = {}
		self._sigchld_read = None
		self._sigchld_write = None
		self._sigchld_src_id = None
		self._pid = os.getpid()

	def _new_source_id(self):
		"""
		Generate a new source id. This method is thread-safe.
		"""
		with self._thread_rlock:
			self._event_handler_id += 1
			return self._event_handler_id

	def _poll(self, timeout=None):
		"""
		All poll() calls pass through here. The poll events
		are added directly to self._poll_event_queue.
		In order to avoid endless blocking, this raises
		StopIteration if timeout is None and there are
		no file descriptors to poll.
		"""

		if timeout is None and \
			not self._poll_event_handlers:
			raise StopIteration(
				"timeout is None and there are no poll() event handlers")

		while True:
			try:
				self._poll_event_queue.extend(self._poll_obj.poll(timeout))
				break
			except (IOError, select.error) as e:
				# Silently handle EINTR, which is normal when we have
				# received a signal such as SIGINT (epoll objects may
				# raise IOError rather than select.error, at least in
				# Python 3.2).
				if not (e.args and e.args[0] == errno.EINTR):
					writemsg_level("\n!!! select error: %s\n" % (e,),
						level=logging.ERROR, noiselevel=-1)
				del e

				# This typically means that we've received a SIGINT, so
				# raise StopIteration in order to break out of our current
				# iteration and respond appropriately to the signal as soon
				# as possible.
				raise StopIteration("interrupted")

	def iteration(self, *args):
		"""
		Like glib.MainContext.iteration(), runs a single iteration. In order
		to avoid blocking forever when may_block is True (the default),
		callers must be careful to ensure that at least one of the following
		conditions is met:
			1) An event source or timeout is registered which is guaranteed
				to trigger at least on event (a call to an idle function
				only counts as an event if it returns a False value which
				causes it to stop being called)
			2) Another thread is guaranteed to call one of the thread-safe
				methods which notify iteration to stop waiting (such as
				idle_add or timeout_add).
		These rules ensure that iteration is able to block until an event
		arrives, without doing any busy waiting that would waste CPU time.
		@type may_block: bool
		@param may_block: if True the call may block waiting for an event
			(default is True).
		@rtype: bool
		@return: True if events were dispatched.
		"""

		may_block = True

		if args:
			if len(args) > 1:
				raise TypeError(
					"expected at most 1 argument (%s given)" % len(args))
			may_block = args[0]

		event_queue =  self._poll_event_queue
		event_handlers = self._poll_event_handlers
		events_handled = 0
		timeouts_checked = False

		if not event_handlers:
			with self._thread_condition:
				if self._run_timeouts():
					events_handled += 1
				timeouts_checked = True
				if not event_handlers and not events_handled and may_block:
					# Block so that we don't waste cpu time by looping too
					# quickly. This makes EventLoop useful for code that needs
					# to wait for timeout callbacks regardless of whether or
					# not any IO handlers are currently registered.
					timeout = self._get_poll_timeout()
					if timeout is None:
						wait_timeout = None
					else:
						wait_timeout = timeout / 1000
					# NOTE: In order to avoid a possible infinite wait when
					# wait_timeout is None, the previous _run_timeouts()
					# call must have returned False *with* _thread_condition
					# acquired. Otherwise, we would risk going to sleep after
					# our only notify event has already passed.
					self._thread_condition.wait(wait_timeout)
					if self._run_timeouts():
						events_handled += 1
					timeouts_checked = True

			# If any timeouts have executed, then return immediately,
			# in order to minimize latency in termination of iteration
			# loops that they may control.
			if events_handled or not event_handlers:
				return bool(events_handled)

		if not event_queue:

			if may_block:
				timeout = self._get_poll_timeout()

				# Avoid blocking for IO if there are any timeout
				# or idle callbacks available to process.
				if timeout != 0 and not timeouts_checked:
					if self._run_timeouts():
						events_handled += 1
					timeouts_checked = True
					if events_handled:
						# Minimize latency for loops controlled
						# by timeout or idle callback events.
						timeout = 0
			else:
				timeout = 0

			try:
				self._poll(timeout=timeout)
			except StopIteration:
				# This can be triggered by EINTR which is caused by signals.
				pass

		# NOTE: IO event handlers may be re-entrant, in case something
		# like AbstractPollTask._wait_loop() needs to be called inside
		# a handler for some reason.
		while event_queue:
			events_handled += 1
			f, event = event_queue.pop()
			try:
				x = event_handlers[f]
			except KeyError:
				# This is known to be triggered by the epoll
				# implementation in qemu-user-1.2.2, and appears
				# to be harmless (see bug #451326).
				continue
			if not x.callback(f, event, *x.args):
				self.source_remove(x.source_id)

		if not timeouts_checked:
			if self._run_timeouts():
				events_handled += 1
			timeouts_checked = True

		return bool(events_handled)

	def _get_poll_timeout(self):

		with self._thread_rlock:
			if self._child_handlers:
				if self._timeout_interval is None:
					timeout = self._sigchld_interval
				else:
					timeout = min(self._sigchld_interval,
						self._timeout_interval)
			else:
				timeout = self._timeout_interval

		return timeout

	def child_watch_add(self, pid, callback, data=None):
		"""
		Like glib.child_watch_add(), sets callback to be called with the
		user data specified by data when the child indicated by pid exits.
		The signature for the callback is:

			def callback(pid, condition, user_data)

		where pid is is the child process id, condition is the status
		information about the child process and user_data is data.

		@type int
		@param pid: process id of a child process to watch
		@type callback: callable
		@param callback: a function to call
		@type data: object
		@param data: the optional data to pass to function
		@rtype: int
		@return: an integer ID
		"""
		source_id = self._new_source_id()
		self._child_handlers[source_id] = self._child_callback_class(
			callback=callback, data=data, pid=pid, source_id=source_id)

		if self._use_signal:
			if self._sigchld_read is None:
				self._sigchld_read, self._sigchld_write = os.pipe()

				fcntl.fcntl(self._sigchld_read, fcntl.F_SETFL,
					fcntl.fcntl(self._sigchld_read,
					fcntl.F_GETFL) | os.O_NONBLOCK)

				# FD_CLOEXEC is enabled by default in Python >=3.4.
				if sys.hexversion < 0x3040000:
					try:
						fcntl.FD_CLOEXEC
					except AttributeError:
						pass
					else:
						fcntl.fcntl(self._sigchld_read, fcntl.F_SETFD,
							fcntl.fcntl(self._sigchld_read,
							fcntl.F_GETFD) | fcntl.FD_CLOEXEC)

			# The IO watch is dynamically registered and unregistered as
			# needed, since we don't want to consider it as a valid source
			# of events when there are no child listeners. It's important
			# to distinguish when there are no valid sources of IO events,
			# in order to avoid an endless poll call if there's no timeout.
			if self._sigchld_src_id is None:
				self._sigchld_src_id = self.io_add_watch(
					self._sigchld_read, self.IO_IN, self._sigchld_io_cb)
				signal.signal(signal.SIGCHLD, self._sigchld_sig_cb)

		# poll now, in case the SIGCHLD has already arrived
		self._poll_child_processes()
		return source_id

	def _sigchld_sig_cb(self, signum, frame):
		# If this signal handler was not installed by the
		# current process then the signal doesn't belong to
		# this EventLoop instance.
		if os.getpid() == self._pid:
			os.write(self._sigchld_write, b'\0')

	def _sigchld_io_cb(self, fd, events):
		try:
			while True:
				os.read(self._sigchld_read, 4096)
		except OSError:
			# read until EAGAIN
			pass
		self._poll_child_processes()
		return True

	def _poll_child_processes(self):
		if not self._child_handlers:
			return False

		calls = 0

		for x in list(self._child_handlers.values()):
			if x.source_id not in self._child_handlers:
				# it's already been called via re-entrance
				continue
			try:
				wait_retval = os.waitpid(x.pid, os.WNOHANG)
			except OSError as e:
				if e.errno != errno.ECHILD:
					raise
				del e
				self.source_remove(x.source_id)
			else:
				# With waitpid and WNOHANG, only check the
				# first element of the tuple since the second
				# element may vary (bug #337465).
				if wait_retval[0] != 0:
					calls += 1
					self.source_remove(x.source_id)
					x.callback(x.pid, wait_retval[1], x.data)

		return bool(calls)

	def idle_add(self, callback, *args):
		"""
		Like glib.idle_add(), if callback returns False it is
		automatically removed from the list of event sources and will
		not be called again. This method is thread-safe.

		@type callback: callable
		@param callback: a function to call
		@rtype: int
		@return: an integer ID
		"""
		with self._thread_condition:
			source_id = self._new_source_id()
			self._idle_callbacks[source_id] = self._idle_callback_class(
				args=args, callback=callback, source_id=source_id)
			self._thread_condition.notify()
		return source_id

	def _run_idle_callbacks(self):
		# assumes caller has acquired self._thread_rlock
		if not self._idle_callbacks:
			return False
		state_change = 0
		# Iterate of our local list, since self._idle_callbacks can be
		# modified during the exection of these callbacks.
		for x in list(self._idle_callbacks.values()):
			if x.source_id not in self._idle_callbacks:
				# it got cancelled while executing another callback
				continue
			if x.calling:
				# don't call it recursively
				continue
			x.calling = True
			try:
				if not x.callback(*x.args):
					state_change += 1
					self.source_remove(x.source_id)
			finally:
				x.calling = False

		return bool(state_change)

	def timeout_add(self, interval, function, *args):
		"""
		Like glib.timeout_add(), interval argument is the number of
		milliseconds between calls to your function, and your function
		should return False to stop being called, or True to continue
		being called. Any additional positional arguments given here
		are passed to your function when it's called. This method is
		thread-safe.
		"""
		with self._thread_condition:
			source_id = self._new_source_id()
			self._timeout_handlers[source_id] = \
				self._timeout_handler_class(
					interval=interval, function=function, args=args,
					source_id=source_id, timestamp=time.time())
			if self._timeout_interval is None or \
				self._timeout_interval > interval:
				self._timeout_interval = interval
			self._thread_condition.notify()
		return source_id

	def _run_timeouts(self):

		calls = 0
		if not self._use_signal:
			if self._poll_child_processes():
				calls += 1

		with self._thread_rlock:

			if self._run_idle_callbacks():
				calls += 1

			if not self._timeout_handlers:
				return bool(calls)

			ready_timeouts = []
			current_time = time.time()
			for x in self._timeout_handlers.values():
				elapsed_seconds = current_time - x.timestamp
				# elapsed_seconds < 0 means the system clock has been adjusted
				if elapsed_seconds < 0 or \
					(x.interval - 1000 * elapsed_seconds) <= 0:
					ready_timeouts.append(x)

			# Iterate of our local list, since self._timeout_handlers can be
			# modified during the exection of these callbacks.
			for x in ready_timeouts:
				if x.source_id not in self._timeout_handlers:
					# it got cancelled while executing another timeout
					continue
				if x.calling:
					# don't call it recursively
					continue
				calls += 1
				x.calling = True
				try:
					x.timestamp = time.time()
					if not x.function(*x.args):
						self.source_remove(x.source_id)
				finally:
					x.calling = False

		return bool(calls)

	def io_add_watch(self, f, condition, callback, *args):
		"""
		Like glib.io_add_watch(), your function should return False to
		stop being called, or True to continue being called. Any
		additional positional arguments given here are passed to your
		function when it's called.

		@type f: int or object with fileno() method
		@param f: a file descriptor to monitor
		@type condition: int
		@param condition: a condition mask
		@type callback: callable
		@param callback: a function to call
		@rtype: int
		@return: an integer ID of the event source
		"""
		if f in self._poll_event_handlers:
			raise AssertionError("fd %d is already registered" % f)
		source_id = self._new_source_id()
		self._poll_event_handler_ids[source_id] = f
		self._poll_event_handlers[f] = self._io_handler_class(
			args=args, callback=callback, f=f, source_id=source_id)
		self._poll_obj.register(f, condition)
		return source_id

	def source_remove(self, reg_id):
		"""
		Like glib.source_remove(), this returns True if the given reg_id
		is found and removed, and False if the reg_id is invalid or has
		already been removed.
		"""
		x = self._child_handlers.pop(reg_id, None)
		if x is not None:
			if not self._child_handlers and self._use_signal:
				signal.signal(signal.SIGCHLD, signal.SIG_DFL)
				self.source_remove(self._sigchld_src_id)
				self._sigchld_src_id = None
			return True

		with self._thread_rlock:
			idle_callback = self._idle_callbacks.pop(reg_id, None)
			if idle_callback is not None:
				return True
			timeout_handler = self._timeout_handlers.pop(reg_id, None)
			if timeout_handler is not None:
				if timeout_handler.interval == self._timeout_interval:
					if self._timeout_handlers:
						self._timeout_interval = min(x.interval
							for x in self._timeout_handlers.values())
					else:
						self._timeout_interval = None
				return True

		f = self._poll_event_handler_ids.pop(reg_id, None)
		if f is None:
			return False
		self._poll_obj.unregister(f)
		if self._poll_event_queue:
			# Discard any unhandled events that belong to this file,
			# in order to prevent these events from being erroneously
			# delivered to a future handler that is using a reallocated
			# file descriptor of the same numeric value (causing
			# extremely confusing bugs).
			remaining_events = []
			discarded_events = False
			for event in self._poll_event_queue:
				if event[0] == f:
					discarded_events = True
				else:
					remaining_events.append(event)

			if discarded_events:
				self._poll_event_queue[:] = remaining_events

		del self._poll_event_handlers[f]
		return True

	def run_until_complete(self, future):
		"""
		Run until the Future is done.

		@type future: asyncio.Future
		@param future: a Future to wait for
		@rtype: object
		@return: the Future's result
		@raise: the Future's exception
		"""
		while not future.done():
			self.iteration()

		return future.result()

_can_poll_device = None

def can_poll_device():
	"""
	Test if it's possible to use poll() on a device such as a pty. This
	is known to fail on Darwin.
	@rtype: bool
	@return: True if poll() on a device succeeds, False otherwise.
	"""

	global _can_poll_device
	if _can_poll_device is not None:
		return _can_poll_device

	if not hasattr(select, "poll"):
		_can_poll_device = False
		return _can_poll_device

	try:
		dev_null = open('/dev/null', 'rb')
	except IOError:
		_can_poll_device = False
		return _can_poll_device

	p = select.poll()
	try:
		p.register(dev_null.fileno(), PollConstants.POLLIN)
	except TypeError:
		# Jython: Object 'org.python.core.io.FileIO@f8f175' is not watchable
		_can_poll_device = False
		return _can_poll_device

	invalid_request = False
	for f, event in p.poll():
		if event & PollConstants.POLLNVAL:
			invalid_request = True
			break
	dev_null.close()

	_can_poll_device = not invalid_request
	return _can_poll_device

def create_poll_instance():
	"""
	Create an instance of select.poll, or an instance of
	PollSelectAdapter there is no poll() implementation or
	it is broken somehow.
	"""
	if can_poll_device():
		return select.poll()
	return PollSelectAdapter()

class _epoll_adapter(object):
	"""
	Wraps a select.epoll instance in order to make it compatible
	with select.poll instances. This is necessary since epoll instances
	interpret timeout arguments differently. Note that the file descriptor
	that is associated with an epoll instance will close automatically when
	it is garbage collected, so it's not necessary to close it explicitly.
	"""
	__slots__ = ('_epoll_obj',)

	def __init__(self, epoll_obj):
		self._epoll_obj = epoll_obj

	def register(self, fd, *args):
		self._epoll_obj.register(fd, *args)

	def unregister(self, fd):
		self._epoll_obj.unregister(fd)

	def poll(self, *args):
		if len(args) > 1:
			raise TypeError(
				"poll expected at most 2 arguments, got " + \
				repr(1 + len(args)))
		timeout = -1
		if args:
			timeout = args[0]
			if timeout is None or timeout < 0:
				timeout = -1
			elif timeout != 0:
				timeout = timeout / 1000

		return self._epoll_obj.poll(timeout)
