# Copyright 2013-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import collections
import errno
import logging
import random
import subprocess

import portage
from portage import _encodings, _unicode_encode
from portage import os
from portage.util import ensure_dirs
from portage.util._async.FileCopier import FileCopier
from portage.util._async.FileDigester import FileDigester
from portage.util._async.PipeLogger import PipeLogger
from portage.util._async.PopenProcess import PopenProcess
from _emerge.CompositeTask import CompositeTask

default_hash_name = portage.const.MANIFEST2_HASH_DEFAULT

# Use --no-check-certificate since Manifest digests should provide
# enough security, and certificates can be self-signed or whatnot.
default_fetchcommand = "wget -c -v -t 1 --passive-ftp --no-check-certificate --timeout=60 -O \"${DISTDIR}/${FILE}\" \"${URI}\""

class FetchTask(CompositeTask):

	__slots__ = ('distfile', 'digests', 'config', 'cpv',
		'restrict', 'uri_tuple', '_current_mirror',
		'_current_stat', '_fetch_tmp_dir_info', '_fetch_tmp_file',
		'_fs_mirror_stack', '_mirror_stack',
		'_previously_added',
		'_primaryuri_stack', '_log_path', '_tried_uris')

	def _start(self):

		if self.config.options.fetch_log_dir is not None and \
			not self.config.options.dry_run:
			self._log_path = os.path.join(
				self.config.options.fetch_log_dir,
				self.distfile + '.log')

		self._previously_added = True
		if self.config.distfiles_db is not None and \
			self.distfile not in self.config.distfiles_db:
			self._previously_added = False
			# Convert _pkg_str to str in order to prevent pickle problems.
			self.config.distfiles_db[self.distfile] = str(self.cpv)

		if self.config.content_db is not None:
			self.config.content_db.add(self.distfile)

		if not self._have_needed_digests():
			msg = "incomplete digests: %s" % " ".join(self.digests)
			self.scheduler.output(msg, background=self.background,
				log_path=self._log_path)
			self.config.log_failure("%s\t%s\t%s" %
				(self.cpv, self.distfile, msg))
			self.config.file_failures[self.distfile] = self.cpv
			self.returncode = os.EX_OK
			self._async_wait()
			return

		st = None
		for layout in self.config.layouts:
			distfile_path = os.path.join(
				self.config.options.distfiles,
				layout.get_path(self.distfile))
			try:
				st = os.stat(distfile_path)
			except OSError as e:
				if e.errno not in (errno.ENOENT, errno.ESTALE):
					msg = "%s stat failed in %s: %s" % \
						(self.distfile, "distfiles", e)
					self.scheduler.output(msg + '\n', background=True,
						log_path=self._log_path)
					logging.error(msg)
			else:
				break

		size_ok = st is not None and st.st_size == self.digests["size"]

		if not size_ok:
			if self.config.options.dry_run:
				if st is not None:
					logging.info(("dry-run: delete '%s' with "
						"wrong size from distfiles") % (self.distfile,))
			else:
				# Do the unlink in order to ensure that the path is clear,
				# even if stat raised ENOENT, since a broken symlink can
				# trigger ENOENT.
				unlink_success = True
				for layout in self.config.layouts:
					unlink_path = os.path.join(
						self.config.options.distfiles,
						layout.get_path(self.distfile))
					if self._unlink_file(unlink_path, "distfiles"):
						if st is not None:
							logging.debug(("delete '%s' with "
								"wrong size from distfiles") % (self.distfile,))
					else:
						self.config.log_failure("%s\t%s\t%s" %
							(self.cpv, self.distfile, "unlink failed in distfiles"))
						unlink_success = False
				if not unlink_success:
					self.returncode = os.EX_OK
					self._async_wait()
					return

		if size_ok:
			if self.config.options.verify_existing_digest:
				self._start_task(
					FileDigester(file_path=distfile_path,
						hash_names=(self._select_hash(),),
						background=self.background,
						logfile=self._log_path), self._distfiles_digester_exit)
				return

			self._success()
			self.returncode = os.EX_OK
			self._async_wait()
			return

		self._start_fetch()

	def _success(self):
		if not self._previously_added:
			size = self.digests["size"]
			self.config.added_byte_count += size
			self.config.added_file_count += 1
			self.config.log_success("%s\t%s\tadded %i bytes" %
				(self.cpv, self.distfile, size))

		if self._log_path is not None:
			if not self.config.options.dry_run:
				try:
					os.unlink(self._log_path)
				except OSError:
					pass

		if self.config.options.recycle_dir is not None:

			recycle_file = os.path.join(
				self.config.options.recycle_dir, self.distfile)

			if self.config.options.dry_run:
				if os.path.exists(recycle_file):
					logging.info("dry-run: delete '%s' from recycle" %
						(self.distfile,))
			else:
				try:
					os.unlink(recycle_file)
				except OSError:
					pass
				else:
					logging.debug("delete '%s' from recycle" %
						(self.distfile,))

	def _distfiles_digester_exit(self, digester):

		self._assert_current(digester)
		if self._was_cancelled():
			self.wait()
			return

		if self._default_exit(digester) != os.EX_OK:
			# IOError reading file in our main distfiles directory? This
			# is a bad situation which normally does not occur, so
			# skip this file and report it, in order to draw attention
			# from the administrator.
			msg = "%s distfiles digester failed unexpectedly" % \
				(self.distfile,)
			self.scheduler.output(msg + '\n', background=True,
				log_path=self._log_path)
			logging.error(msg)
			self.config.log_failure("%s\t%s\t%s" %
				(self.cpv, self.distfile, msg))
			self.config.file_failures[self.distfile] = self.cpv
			self.wait()
			return

		wrong_digest = self._find_bad_digest(digester.digests)
		if wrong_digest is None:
			self._success()
			self.returncode = os.EX_OK
			self.wait()
			return

		self._start_fetch()

	_mirror_info = collections.namedtuple('_mirror_info',
		'name location')

	def _start_fetch(self):

		self._previously_added = False
		self._fs_mirror_stack = []
		if self.config.options.distfiles_local is not None:
			self._fs_mirror_stack.append(self._mirror_info(
				'distfiles-local', self.config.options.distfiles_local))
		if self.config.options.recycle_dir is not None:
			self._fs_mirror_stack.append(self._mirror_info(
				'recycle', self.config.options.recycle_dir))

		self._primaryuri_stack = []
		self._mirror_stack = []
		for uri in reversed(self.uri_tuple):
			if uri.startswith('mirror://'):
				self._mirror_stack.append(
					self._mirror_iterator(uri, self.config.mirrors))
			else:
				self._primaryuri_stack.append(uri)

		self._tried_uris = set()
		self._try_next_mirror()

	@staticmethod
	def _mirror_iterator(uri, mirrors_dict):

		slash_index = uri.find("/", 9)
		if slash_index != -1:
			mirror_name = uri[9:slash_index].strip("/")
			mirrors = mirrors_dict.get(mirror_name)
			if not mirrors:
				return
			mirrors = list(mirrors)
			while mirrors:
				mirror = mirrors.pop(random.randint(0, len(mirrors) - 1))
				yield mirror.rstrip("/") + "/" + uri[slash_index+1:]

	def _try_next_mirror(self):
		if self._fs_mirror_stack:
			self._fetch_fs(self._fs_mirror_stack.pop())
			return
		uri = self._next_uri()
		if uri is not None:
			self._tried_uris.add(uri)
			self._fetch_uri(uri)
			return

		if self._tried_uris:
			msg = "all uris failed"
		else:
			msg = "no fetchable uris"

		self.config.log_failure("%s\t%s\t%s" %
			(self.cpv, self.distfile, msg))
		self.config.file_failures[self.distfile] = self.cpv
		self.returncode = os.EX_OK
		self.wait()

	def _next_uri(self):
		remaining_tries = self.config.options.tries - len(self._tried_uris)
		if remaining_tries > 0:

			if remaining_tries <= self.config.options.tries // 2:
				while self._primaryuri_stack:
					uri = self._primaryuri_stack.pop()
					if uri not in self._tried_uris:
						return uri

			while self._mirror_stack:
				uri = next(self._mirror_stack[-1], None)
				if uri is None:
					self._mirror_stack.pop()
				else:
					if uri not in self._tried_uris:
						return uri

			while self._primaryuri_stack:
				uri = self._primaryuri_stack.pop()
				if uri not in self._tried_uris:
					return uri

		return None

	def _fetch_fs(self, mirror_info):
		file_path = os.path.join(mirror_info.location, self.distfile)

		st = None
		size_ok = False
		try:
			st = os.stat(file_path)
		except OSError as e:
			if e.errno not in (errno.ENOENT, errno.ESTALE):
				msg = "%s stat failed in %s: %s" % \
					(self.distfile, mirror_info.name, e)
				self.scheduler.output(msg + '\n', background=True,
					log_path=self._log_path)
				logging.error(msg)
		else:
			size_ok = st.st_size == self.digests["size"]
			self._current_stat = st

		if size_ok:
			self._current_mirror = mirror_info
			self._start_task(
				FileDigester(file_path=file_path,
					hash_names=(self._select_hash(),),
					background=self.background,
					logfile=self._log_path),
				self._fs_mirror_digester_exit)
		else:
			self._try_next_mirror()

	def _fs_mirror_digester_exit(self, digester):

		self._assert_current(digester)
		if self._was_cancelled():
			self.wait()
			return

		current_mirror = self._current_mirror
		if digester.returncode != os.EX_OK:
			msg = "%s %s digester failed unexpectedly" % \
			(self.distfile, current_mirror.name)
			self.scheduler.output(msg + '\n', background=True,
				log_path=self._log_path)
			logging.error(msg)
		else:
			bad_digest = self._find_bad_digest(digester.digests)
			if bad_digest is not None:
				msg = "%s %s has bad %s digest: expected %s, got %s" % \
					(self.distfile, current_mirror.name, bad_digest,
					self.digests[bad_digest], digester.digests[bad_digest])
				self.scheduler.output(msg + '\n', background=True,
					log_path=self._log_path)
				logging.error(msg)
			elif self.config.options.dry_run:
				# Report success without actually touching any files
				if self._same_device(current_mirror.location,
					self.config.options.distfiles):
					logging.info(("dry-run: hardlink '%s' from %s "
						"to distfiles") % (self.distfile, current_mirror.name))
				else:
					logging.info("dry-run: copy '%s' from %s to distfiles" %
						(self.distfile, current_mirror.name))
				self._success()
				self.returncode = os.EX_OK
				self.wait()
				return
			else:
				src = os.path.join(current_mirror.location, self.distfile)
				dest = os.path.join(self.config.options.distfiles,
						self.config.layouts[0].get_path(self.distfile))
				if self._hardlink_atomic(src, dest,
					"%s to %s" % (current_mirror.name, "distfiles")):
					logging.debug("hardlink '%s' from %s to distfiles" %
						(self.distfile, current_mirror.name))
					self._success()
					self.returncode = os.EX_OK
					self.wait()
					return

				self._start_task(
					FileCopier(src_path=src, dest_path=dest,
						background=(self.background and
							self._log_path is not None),
						logfile=self._log_path),
					self._fs_mirror_copier_exit)
				return

		self._try_next_mirror()

	def _fs_mirror_copier_exit(self, copier):

		self._assert_current(copier)
		if self._was_cancelled():
			self.wait()
			return

		current_mirror = self._current_mirror
		if copier.returncode != os.EX_OK:
			msg = "%s %s copy failed unexpectedly: %s" % \
				(self.distfile, current_mirror.name, copier.future.exception())
			self.scheduler.output(msg + '\n', background=True,
				log_path=self._log_path)
			logging.error(msg)
		else:

			logging.debug("copy '%s' from %s to distfiles" %
				(self.distfile, current_mirror.name))

			# Apply the timestamp from the source file, but
			# just rely on umask for permissions.
			try:
				os.utime(copier.dest_path,
					ns=(self._current_stat.st_mtime_ns,
					self._current_stat.st_mtime_ns))
			except OSError as e:
				msg = "%s %s utime failed unexpectedly: %s" % \
					(self.distfile, current_mirror.name, e)
				self.scheduler.output(msg + '\n', background=True,
					log_path=self._log_path)
				logging.error(msg)

			self._success()
			self.returncode = os.EX_OK
			self.wait()
			return

		self._try_next_mirror()

	def _fetch_uri(self, uri):

		if self.config.options.dry_run:
			# Simply report success.
			logging.info("dry-run: fetch '%s' from '%s'" %
				(self.distfile, uri))
			self._success()
			self.returncode = os.EX_OK
			self._async_wait()
			return

		if self.config.options.temp_dir:
			self._fetch_tmp_dir_info = 'temp-dir'
			distdir = self.config.options.temp_dir
		else:
			self._fetch_tmp_dir_info = 'distfiles'
			distdir = self.config.options.distfiles

		tmp_basename = self.distfile + '._emirrordist_fetch_.%s' % portage.getpid()

		variables = {
			"DISTDIR": distdir,
			"URI":     uri,
			"FILE":    tmp_basename
		}

		self._fetch_tmp_file = os.path.join(distdir, tmp_basename)

		try:
			os.unlink(self._fetch_tmp_file)
		except OSError:
			pass

		args = portage.util.shlex_split(default_fetchcommand)
		args = [portage.util.varexpand(x, mydict=variables)
			for x in args]

		args = [_unicode_encode(x,
			encoding=_encodings['fs'], errors='strict') for x in args]

		null_fd = os.open(os.devnull, os.O_RDONLY)
		fetcher = PopenProcess(background=self.background,
			proc=subprocess.Popen(args, stdin=null_fd,
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT),
			scheduler=self.scheduler)
		os.close(null_fd)

		fetcher.pipe_reader = PipeLogger(background=self.background,
			input_fd=fetcher.proc.stdout, log_file_path=self._log_path,
			scheduler=self.scheduler)

		self._start_task(fetcher, self._fetcher_exit)

	def _fetcher_exit(self, fetcher):

		self._assert_current(fetcher)
		if self._was_cancelled():
			self.wait()
			return

		if os.path.exists(self._fetch_tmp_file):
			self._start_task(
				FileDigester(file_path=self._fetch_tmp_file,
					hash_names=(self._select_hash(),),
					background=self.background,
					logfile=self._log_path),
					self._fetch_digester_exit)
		else:
			self._try_next_mirror()

	def _fetch_digester_exit(self, digester):

		self._assert_current(digester)
		if self._was_cancelled():
			self.wait()
			return

		if digester.returncode != os.EX_OK:
			msg = "%s %s digester failed unexpectedly" % \
			(self.distfile, self._fetch_tmp_dir_info)
			self.scheduler.output(msg + '\n', background=True,
				log_path=self._log_path)
			logging.error(msg)
		else:
			bad_digest = self._find_bad_digest(digester.digests)
			if bad_digest is not None:
				msg = "%s has bad %s digest: expected %s, got %s" % \
					(self.distfile, bad_digest,
					self.digests[bad_digest], digester.digests[bad_digest])
				self.scheduler.output(msg + '\n', background=True,
					log_path=self._log_path)
				try:
					os.unlink(self._fetch_tmp_file)
				except OSError:
					pass
			else:
				dest = os.path.join(self.config.options.distfiles,
						self.config.layouts[0].get_path(self.distfile))
				ensure_dirs(os.path.dirname(dest))
				try:
					os.rename(self._fetch_tmp_file, dest)
				except OSError:
					self._start_task(
						FileCopier(src_path=self._fetch_tmp_file,
							dest_path=dest,
							background=(self.background and
								self._log_path is not None),
							logfile=self._log_path),
						self._fetch_copier_exit)
					return
				else:
					self._make_layout_links()
					return

		self._try_next_mirror()

	def _fetch_copier_exit(self, copier):

		self._assert_current(copier)

		try:
			os.unlink(self._fetch_tmp_file)
		except OSError:
			pass

		if self._was_cancelled():
			self.wait()
			return

		if copier.returncode == os.EX_OK:
			self._make_layout_links()
		else:
			# out of space?
			msg = "%s %s copy failed unexpectedly: %s" % \
				(self.distfile, self._fetch_tmp_dir_info, copier.future.exception())
			self.scheduler.output(msg + '\n', background=True,
				log_path=self._log_path)
			logging.error(msg)
			self.config.log_failure("%s\t%s\t%s" %
				(self.cpv, self.distfile, msg))
			self.config.file_failures[self.distfile] = self.cpv
			self.returncode = 1
			self.wait()

	def _make_layout_links(self):
		dist_path = None
		success = True
		for layout in self.config.layouts[1:]:
			if dist_path is None:
				dist_path = os.path.join(self.config.options.distfiles,
						self.config.layouts[0].get_path(self.distfile))
			link_path = os.path.join(self.config.options.distfiles,
					layout.get_path(self.distfile))
			ensure_dirs(os.path.dirname(link_path))
			src_path = dist_path
			if self.config.options.symlinks:
				src_path = os.path.relpath(dist_path,
						os.path.dirname(link_path))

			if not self._hardlink_atomic(src_path, link_path,
					"%s -> %s" % (link_path, src_path),
					self.config.options.symlinks):
				success = False
				break

		if success:
			self._success()
			self.returncode = os.EX_OK
		else:
			msg = "failed to create distfiles layout {}".format(
				"symlink" if self.config.options.symlinks else "hardlink")
			self.config.log_failure("%s\t%s\t%s" %
				(self.cpv, self.distfile, msg))
			self.config.file_failures[self.distfile] = self.cpv
			self.returncode = 1

		self.wait()

	def _unlink_file(self, file_path, dir_info):
		try:
			os.unlink(file_path)
		except OSError as e:
			if e.errno not in (errno.ENOENT, errno.ESTALE):
				msg = "unlink '%s' failed in %s: %s" % \
					(self.distfile, dir_info, e)
				self.scheduler.output(msg + '\n', background=True,
					log_path=self._log_path)
				logging.error(msg)
				return False
		return True

	def _have_needed_digests(self):
		return "size" in self.digests and \
			self._select_hash() is not None

	def _select_hash(self):
		if default_hash_name in self.digests:
			return default_hash_name
		for hash_name in self.digests:
			if hash_name != "size" and \
				hash_name in portage.checksum.get_valid_checksum_keys():
				return hash_name

		return None

	def _find_bad_digest(self, digests):
		for hash_name, hash_value in digests.items():
			if self.digests[hash_name] != hash_value:
				return hash_name
		return None

	@staticmethod
	def _same_device(path1, path2):
		try:
			st1 = os.stat(path1)
			st2 = os.stat(path2)
		except OSError:
			return False
		else:
			return st1.st_dev == st2.st_dev

	def _hardlink_atomic(self, src, dest, dir_info, symlink=False):

		head, tail = os.path.split(dest)
		hardlink_tmp = os.path.join(head, ".%s._mirrordist_hardlink_.%s" % \
			(tail, portage.getpid()))

		try:
			try:
				if symlink:
					os.symlink(src, hardlink_tmp)
				else:
					os.link(src, hardlink_tmp)
			except OSError as e:
				if e.errno != errno.EXDEV:
					msg = "hardlink %s from %s failed: %s" % \
						(self.distfile, dir_info, e)
					self.scheduler.output(msg + '\n', background=True,
						log_path=self._log_path)
					logging.error(msg)
				return False

			try:
				os.rename(hardlink_tmp, dest)
			except OSError as e:
				msg = "hardlink rename '%s' from %s failed: %s" % \
					(self.distfile, dir_info, e)
				self.scheduler.output(msg + '\n', background=True,
					log_path=self._log_path)
				logging.error(msg)
				return False
		finally:
			try:
				os.unlink(hardlink_tmp)
			except OSError:
				pass

		return True
