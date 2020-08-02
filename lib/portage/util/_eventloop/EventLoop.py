# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from __future__ import division

import collections
import errno
import functools
import logging
import os
import select
import signal
import time
import traceback

import asyncio as _real_asyncio

try:
	import fcntl
except ImportError:
	#  http://bugs.jython.org/issue1074
	fcntl = None

try:
	import threading
except ImportError:
	import dummy_threading as threading

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util.futures:asyncio',
	'portage.util.futures.executor.fork:ForkExecutor',
	'portage.util.futures.unix_events:_PortageEventLoop,_PortageChildWatcher',
)

from portage.util import writemsg_level
from ..SlotObject import SlotObject
from .PollConstants import PollConstants
from .PollSelectAdapter import PollSelectAdapter

class EventLoop:
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
		__slots__ = ("_args", "_callback", "_cancelled")

	class _io_handler_class(SlotObject):
		__slots__ = ("args", "callback", "f", "source_id")

	class _timeout_handler_class(SlotObject):
		__slots__ = ("args", "function", "calling", "interval", "source_id",
			"timestamp")

	class _handle:
		"""
		A callback wrapper object, compatible with asyncio.Handle.
		"""
		__slots__ = ("_callback_id", "_loop")

		def __init__(self, callback_id, loop):
			self._callback_id = callback_id
			self._loop = loop

		def cancel(self):
			"""
			Cancel the call. If the callback is already canceled or executed,
			this method has no effect.
			"""
			self._loop.source_remove(self._callback_id)

	class _call_soon_callback:
		"""
		Wraps a call_soon callback, and always returns False, since these
		callbacks are only supposed to run once.
		"""
		__slots__ = ("_args", "_callback")

		def __init__(self, callback, args):
			self._callback = callback
			self._args = args

		def __call__(self):
			self._callback(*self._args)
			return False

	class _selector_callback:
		"""
		Wraps an callback, and always returns True, for callbacks that
		are supposed to run repeatedly.
		"""
		__slots__ = ("_args", "_callbacks")

		def __init__(self, callbacks):
			self._callbacks = callbacks

		def __call__(self, fd, event):
			for callback, mask in self._callbacks:
				if event & mask:
					callback()
			return True

	def __init__(self, main=True):
		"""
		@param main: If True then this is a singleton instance for use
			in the main thread, otherwise it is a local instance which
			can safely be use in a non-main thread (default is True, so
			that global_event_loop does not need constructor arguments)
		@type main: bool
		"""
		self._use_signal = main and fcntl is not None
		self._debug = bool(os.environ.get('PYTHONASYNCIODEBUG'))
		self._thread_rlock = threading.RLock()
		self._thread_condition = threading.Condition(self._thread_rlock)
		self._poll_event_queue = []
		self._poll_event_handlers = {}
		self._poll_event_handler_ids = {}
		# Number of current calls to self.iteration(). A number greater
		# than 1 indicates recursion, which is not supported by asyncio's
		# default event loop.
		self._iteration_depth = 0
		# Increment id for each new handler.
		self._event_handler_id = 0
		# New call_soon callbacks must have an opportunity to
		# execute before it's safe to wait on self._thread_condition
		# without a timeout, since delaying its execution indefinitely
		# could lead to a deadlock. The following attribute stores the
		# event handler id of the most recently added call_soon callback.
		# If this attribute has changed since the last time that the
		# call_soon callbacks have been called, then it's not safe to
		# wait on self._thread_condition without a timeout.
		self._call_soon_id = None
		# Use deque, with thread-safe append, in order to emulate the FIFO
		# queue behavior of the AbstractEventLoop.call_soon method.
		self._idle_callbacks = collections.deque()
		self._idle_callbacks_remaining = 0
		self._timeout_handlers = {}
		self._timeout_interval = None
		self._default_executor = None

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

		# These trigger both reader and writer callbacks.
		EVENT_SHARED = self.IO_HUP | self.IO_ERR | self.IO_NVAL

		self._EVENT_READ = self.IO_IN | EVENT_SHARED
		self._EVENT_WRITE = self.IO_OUT | EVENT_SHARED

		self._child_handlers = {}
		self._sigchld_read = None
		self._sigchld_write = None
		self._sigchld_src_id = None
		self._pid = os.getpid()
		self._asyncio_wrapper = _PortageEventLoop(loop=self)
		self._asyncio_child_watcher = _PortageChildWatcher(self)

	def create_future(self):
		"""
		Create a Future object attached to the loop.
		"""
		return asyncio.Future(loop=self._asyncio_wrapper)

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
		self._iteration_depth += 1
		try:
			return self._iteration(*args)
		finally:
			self._iteration_depth -= 1

	def _iteration(self, *args):
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
				prev_call_soon_id = self._call_soon_id
				if self._run_timeouts():
					events_handled += 1
				timeouts_checked = True

				call_soon = prev_call_soon_id is not self._call_soon_id
				if self._call_soon_id is not None and self._call_soon_id._cancelled:
					# Allow garbage collection of cancelled callback.
					self._call_soon_id = None

				if (not call_soon and not event_handlers
					and not events_handled and may_block):
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

			# The IO watch is dynamically registered and unregistered as
			# needed, since we don't want to consider it as a valid source
			# of events when there are no child listeners. It's important
			# to distinguish when there are no valid sources of IO events,
			# in order to avoid an endless poll call if there's no timeout.
			if self._sigchld_src_id is None:
				self._sigchld_src_id = self.io_add_watch(
					self._sigchld_read, self.IO_IN, self._sigchld_io_cb)
				signal.signal(signal.SIGCHLD, self._sigchld_sig_cb)

		# poll soon, in case the SIGCHLD has already arrived
		self.call_soon(self._poll_child_processes)
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

		The idle_add method is deprecated. Use the call_soon and
		call_soon_threadsafe methods instead.

		@type callback: callable
		@param callback: a function to call
		@return: a handle which can be used to cancel the callback
			via the source_remove method
		@rtype: object
		"""
		with self._thread_condition:
			source_id = self._idle_add(callback, *args)
			self._thread_condition.notify()
		return source_id

	def _idle_add(self, callback, *args):
		"""Like idle_add(), but without thread safety."""
		# Hold self._thread_condition when assigning self._call_soon_id,
		# since it might be modified via a thread-safe method.
		with self._thread_condition:
			handle = self._call_soon_id = self._idle_callback_class(
				_args=args, _callback=callback)
		# This deque append is thread-safe, but it does *not* notify the
		# loop's thread, so the caller must notify if appropriate.
		self._idle_callbacks.append(handle)
		return handle

	def _run_idle_callbacks(self):
		# assumes caller has acquired self._thread_rlock
		if not self._idle_callbacks:
			return False
		state_change = 0
		reschedule = []
		# Use remaining count to avoid calling any newly scheduled callbacks,
		# since self._idle_callbacks can be modified during the exection of
		# these callbacks. The remaining count can be reset by recursive
		# calls to this method. Recursion must remain supported until all
		# consumers of AsynchronousLock.unlock() have been migrated to the
		# async_unlock() method, see bug 614108.
		self._idle_callbacks_remaining = len(self._idle_callbacks)

		while self._idle_callbacks_remaining:
			self._idle_callbacks_remaining -= 1
			try:
				x = self._idle_callbacks.popleft() # thread-safe
			except IndexError:
				break
			if x._cancelled:
				# it got cancelled while executing another callback
				continue
			if x._callback(*x._args):
				# Reschedule, but not until after it's called, since
				# we don't want it to call itself in a recursive call
				# to this method.
				self._idle_callbacks.append(x)
			else:
				x._cancelled = True
				state_change += 1

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
					source_id=source_id, timestamp=self.time())
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
			current_time = self.time()
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
					x.timestamp = self.time()
					if not x.function(*x.args):
						self.source_remove(x.source_id)
				finally:
					x.calling = False

		return bool(calls)

	def add_reader(self, fd, callback, *args):
		"""
		Start watching the file descriptor for read availability and then
		call the callback with specified arguments.

		Use functools.partial to pass keywords to the callback.
		"""
		handler = self._poll_event_handlers.get(fd)
		callbacks = [(functools.partial(callback, *args), self._EVENT_READ)]
		selector_mask = self._EVENT_READ
		if handler is not None:
			if not isinstance(handler.callback, self._selector_callback):
				raise AssertionError("add_reader called with fd "
					"registered directly via io_add_watch")
			for item in handler.callback._callbacks:
				callback, mask = item
				if mask != self._EVENT_READ:
					selector_mask |= mask
					callbacks.append(item)
			self.source_remove(handler.source_id)
		self.io_add_watch(fd, selector_mask, self._selector_callback(callbacks))

	def remove_reader(self, fd):
		"""
		Stop watching the file descriptor for read availability.
		"""
		handler = self._poll_event_handlers.get(fd)
		if handler is not None:
			if not isinstance(handler.callback, self._selector_callback):
				raise AssertionError("remove_reader called with fd "
					"registered directly via io_add_watch")
			callbacks = []
			selector_mask = 0
			removed = False
			for item in handler.callback._callbacks:
				callback, mask = item
				if mask == self._EVENT_READ:
					removed = True
				else:
					selector_mask |= mask
					callbacks.append(item)
			self.source_remove(handler.source_id)
			if callbacks:
				self.io_add_watch(fd, selector_mask,
					self._selector_callback(callbacks))
			return removed
		return False

	def add_writer(self, fd, callback, *args):
		"""
		Start watching the file descriptor for write availability and then
		call the callback with specified arguments.

		Use functools.partial to pass keywords to the callback.
		"""
		handler = self._poll_event_handlers.get(fd)
		callbacks = [(functools.partial(callback, *args), self._EVENT_WRITE)]
		selector_mask = self._EVENT_WRITE
		if handler is not None:
			if not isinstance(handler.callback, self._selector_callback):
				raise AssertionError("add_reader called with fd "
					"registered directly via io_add_watch")
			for item in handler.callback._callbacks:
				callback, mask = item
				if mask != self._EVENT_WRITE:
					selector_mask |= mask
					callbacks.append(item)
			self.source_remove(handler.source_id)
		self.io_add_watch(fd, selector_mask, self._selector_callback(callbacks))

	def remove_writer(self, fd):
		"""
		Stop watching the file descriptor for write availability.
		"""
		handler = self._poll_event_handlers.get(fd)
		if handler is not None:
			if not isinstance(handler.callback, self._selector_callback):
				raise AssertionError("remove_reader called with fd "
					"registered directly via io_add_watch")
			callbacks = []
			selector_mask = 0
			removed = False
			for item in handler.callback._callbacks:
				callback, mask = item
				if mask == self._EVENT_WRITE:
					removed = True
				else:
					selector_mask |= mask
					callbacks.append(item)
			self.source_remove(handler.source_id)
			if callbacks:
				self.io_add_watch(fd, selector_mask,
					self._selector_callback(callbacks))
			return removed
		return False

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
		if isinstance(reg_id, self._idle_callback_class):
			if not reg_id._cancelled:
				reg_id._cancelled = True
				return True
			return False

		x = self._child_handlers.pop(reg_id, None)
		if x is not None:
			if not self._child_handlers and self._use_signal:
				signal.signal(signal.SIGCHLD, signal.SIG_DFL)
				self.source_remove(self._sigchld_src_id)
				self._sigchld_src_id = None
			return True

		with self._thread_rlock:
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
		future = asyncio.ensure_future(future, loop=self._asyncio_wrapper)

		# Since done callbacks are executed via call_soon, it's desirable
		# to continue iterating until those callbacks have executed, which
		# is easily achieved by registering a done callback and waiting for
		# it to execute.
		waiter = self.create_future()
		future.add_done_callback(waiter.set_result)
		while not waiter.done():
			self.iteration()

		return future.result()

	def call_soon(self, callback, *args, **kwargs):
		"""
		Arrange for a callback to be called as soon as possible. The callback
		is called after call_soon() returns, when control returns to the event
		loop.

		This operates as a FIFO queue, callbacks are called in the order in
		which they are registered. Each callback will be called exactly once.

		Any positional arguments after the callback will be passed to the
		callback when it is called.

		The context argument currently does nothing, but exists for minimal
		interoperability with Future instances that require it for PEP 567.

		An object compatible with asyncio.Handle is returned, which can
		be used to cancel the callback.

		@type callback: callable
		@param callback: a function to call
		@type context: contextvars.Context
		@param context: An optional keyword-only context argument allows
			specifying a custom contextvars.Context for the callback to run
			in. The current context is used when no context is provided.
		@return: a handle which can be used to cancel the callback
		@rtype: asyncio.Handle (or compatible)
		"""
		try:
			unexpected = next(key for key in kwargs if key != 'context')
		except StopIteration:
			pass
		else:
			raise TypeError("call_soon() got an unexpected keyword argument '%s'" % unexpected)
		return self._handle(self._idle_add(
			self._call_soon_callback(callback, args)), self)

	def call_soon_threadsafe(self, callback, *args, **kwargs):
		"""Like call_soon(), but thread safe."""
		try:
			unexpected = next(key for key in kwargs if key != 'context')
		except StopIteration:
			pass
		else:
			raise TypeError("call_soon_threadsafe() got an unexpected keyword argument '%s'" % unexpected)
		# idle_add provides thread safety
		return self._handle(self.idle_add(
			self._call_soon_callback(callback, args)), self)

	def time(self):
		"""Return the time according to the event loop's clock.

		This is a float expressed in seconds since an epoch, but the
		epoch, precision, accuracy and drift are unspecified and may
		differ per event loop.
		"""
		return time.monotonic()

	def call_later(self, delay, callback, *args, **kwargs):
		"""
		Arrange for the callback to be called after the given delay seconds
		(either an int or float).

		An instance of asyncio.Handle is returned, which can be used to cancel
		the callback.

		callback will be called exactly once per call to call_later(). If two
		callbacks are scheduled for exactly the same time, it is undefined
		which will be called first.

		The optional positional args will be passed to the callback when
		it is called. If you want the callback to be called with some named
		arguments, use a closure or functools.partial().

		The context argument currently does nothing, but exists for minimal
		interoperability with Future instances that require it for PEP 567.

		Use functools.partial to pass keywords to the callback.

		@type delay: int or float
		@param delay: delay seconds
		@type callback: callable
		@param callback: a function to call
		@type context: contextvars.Context
		@param context: An optional keyword-only context argument allows
			specifying a custom contextvars.Context for the callback to run
			in. The current context is used when no context is provided.
		@return: a handle which can be used to cancel the callback
		@rtype: asyncio.Handle (or compatible)
		"""
		try:
			unexpected = next(key for key in kwargs if key != 'context')
		except StopIteration:
			pass
		else:
			raise TypeError("call_later() got an unexpected keyword argument '%s'" % unexpected)
		return self._handle(self.timeout_add(
			delay * 1000, self._call_soon_callback(callback, args)), self)

	def call_at(self, when, callback, *args, **kwargs):
		"""
		Arrange for the callback to be called at the given absolute
		timestamp when (an int or float), using the same time reference as
		AbstractEventLoop.time().

		This method's behavior is the same as call_later().

		An instance of asyncio.Handle is returned, which can be used to
		cancel the callback.

		Use functools.partial to pass keywords to the callback.

		@type when: int or float
		@param when: absolute timestamp when to call callback
		@type callback: callable
		@param callback: a function to call
		@type context: contextvars.Context
		@param context: An optional keyword-only context argument allows
			specifying a custom contextvars.Context for the callback to run
			in. The current context is used when no context is provided.
		@return: a handle which can be used to cancel the callback
		@rtype: asyncio.Handle (or compatible)
		"""
		try:
			unexpected = next(key for key in kwargs if key != 'context')
		except StopIteration:
			pass
		else:
			raise TypeError("call_at() got an unexpected keyword argument '%s'" % unexpected)
		delta = when - self.time()
		return self.call_later(delta if delta > 0 else 0, callback, *args)

	def run_in_executor(self, executor, func, *args):
		"""
		Arrange for a func to be called in the specified executor.

		The executor argument should be an Executor instance. The default
		executor is used if executor is None.

		Use functools.partial to pass keywords to the *func*.

		@param executor: executor
		@type executor: concurrent.futures.Executor or None
		@param func: a function to call
		@type func: callable
		@return: a Future
		@rtype: asyncio.Future (or compatible)
		"""
		if executor is None:
			executor = self._default_executor
			if executor is None:
				executor = ForkExecutor(loop=self)
				self._default_executor = executor
		future = executor.submit(func, *args)
		future = _real_asyncio.wrap_future(future,
			loop=self._asyncio_wrapper)
		return future

	def is_running(self):
		"""Return whether the event loop is currently running."""
		return self._iteration_depth > 0

	def is_closed(self):
		"""Returns True if the event loop was closed."""
		return self._poll_obj is None

	def close(self):
		"""Close the event loop.

		This clears the queues and shuts down the executor,
		and waits for it to finish.
		"""
		executor = self._default_executor
		if executor is not None:
			self._default_executor = None
			executor.shutdown(wait=True)

		if self._poll_obj is not None:
			close = getattr(self._poll_obj, 'close', None)
			if close is not None:
				close()
			self._poll_obj = None

	def default_exception_handler(self, context):
		"""
		Default exception handler.

		This is called when an exception occurs and no exception
		handler is set, and can be called by a custom exception
		handler that wants to defer to the default behavior.

		The context parameter has the same meaning as in
		`call_exception_handler()`.

		@param context: exception context
		@type context: dict
		"""
		message = context.get('message')
		if not message:
			message = 'Unhandled exception in event loop'

		exception = context.get('exception')
		if exception is not None:
			exc_info = (type(exception), exception, exception.__traceback__)
		else:
			exc_info = False

		log_lines = [message]
		for key in sorted(context):
			if key in {'message', 'exception'}:
				continue
			value = context[key]
			if key == 'source_traceback':
				tb = ''.join(traceback.format_list(value))
				value = 'Object created at (most recent call last):\n'
				value += tb.rstrip()
			elif key == 'handle_traceback':
				tb = ''.join(traceback.format_list(value))
				value = 'Handle created at (most recent call last):\n'
				value += tb.rstrip()
			else:
				value = repr(value)
			log_lines.append('{}: {}'.format(key, value))

		logging.error('\n'.join(log_lines), exc_info=exc_info)
		os.kill(os.getpid(), signal.SIGTERM)

	def call_exception_handler(self, context):
		"""
		Call the current event loop's exception handler.

		The context argument is a dict containing the following keys:

		- 'message': Error message;
		- 'exception' (optional): Exception object;
		- 'future' (optional): Future instance;
		- 'handle' (optional): Handle instance;
		- 'protocol' (optional): Protocol instance;
		- 'transport' (optional): Transport instance;
		- 'socket' (optional): Socket instance;
		- 'asyncgen' (optional): Asynchronous generator that caused
								the exception.

		New keys may be introduced in the future.

		@param context: exception context
		@type context: dict
		"""
		self.default_exception_handler(context)

	def get_debug(self):
		"""
		Get the debug mode (bool) of the event loop.

		The default value is True if the environment variable
		PYTHONASYNCIODEBUG is set to a non-empty string, False otherwise.
		"""
		return self._debug

	def set_debug(self, enabled):
		"""Set the debug mode of the event loop."""
		self._debug = enabled


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

class _epoll_adapter:
	"""
	Wraps a select.epoll instance in order to make it compatible
	with select.poll instances. This is necessary since epoll instances
	interpret timeout arguments differently. Note that the file descriptor
	that is associated with an epoll instance will close automatically when
	it is garbage collected, so it's not necessary to close it explicitly.
	"""
	__slots__ = ('_epoll_obj', 'close')

	def __init__(self, epoll_obj):
		self._epoll_obj = epoll_obj
		self.close = epoll_obj.close

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
