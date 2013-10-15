# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import logging
import re
import stat
import subprocess

import portage
from portage import os

def chk_updated_info_files(root, infodirs, prev_mtimes):

	if os.path.exists("/usr/bin/install-info"):
		out = portage.output.EOutput()
		regen_infodirs = []
		for z in infodirs:
			if z == '':
				continue
			inforoot = portage.util.normalize_path(root + z)
			if os.path.isdir(inforoot) and \
				not [x for x in os.listdir(inforoot) \
				if x.startswith('.keepinfodir')]:
					infomtime = os.stat(inforoot)[stat.ST_MTIME]
					if inforoot not in prev_mtimes or \
						prev_mtimes[inforoot] != infomtime:
							regen_infodirs.append(inforoot)

		if not regen_infodirs:
			portage.util.writemsg_stdout("\n")
			if portage.util.noiselimit >= 0:
				out.einfo("GNU info directory index is up-to-date.")
		else:
			portage.util.writemsg_stdout("\n")
			if portage.util.noiselimit >= 0:
				out.einfo("Regenerating GNU info directory index...")

			dir_extensions = ("", ".gz", ".bz2")
			icount = 0
			badcount = 0
			errmsg = ""
			for inforoot in regen_infodirs:
				if inforoot == '':
					continue

				if not os.path.isdir(inforoot) or \
					not os.access(inforoot, os.W_OK):
					continue

				file_list = os.listdir(inforoot)
				file_list.sort()
				dir_file = os.path.join(inforoot, "dir")
				moved_old_dir = False
				processed_count = 0
				for x in file_list:
					if x.startswith(".") or \
						os.path.isdir(os.path.join(inforoot, x)):
						continue
					if x.startswith("dir"):
						skip = False
						for ext in dir_extensions:
							if x == "dir" + ext or \
								x == "dir" + ext + ".old":
								skip = True
								break
						if skip:
							continue
					if processed_count == 0:
						for ext in dir_extensions:
							try:
								os.rename(dir_file + ext, dir_file + ext + ".old")
								moved_old_dir = True
							except EnvironmentError as e:
								if e.errno != errno.ENOENT:
									raise
								del e
					processed_count += 1
					try:
						proc = subprocess.Popen(
							['/usr/bin/install-info',
							'--dir-file=%s' % os.path.join(inforoot, "dir"),
							os.path.join(inforoot, x)],
							env=dict(os.environ, LANG="C", LANGUAGE="C"),
							stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
					except OSError:
						myso = None
					else:
						myso = portage._unicode_decode(
							proc.communicate()[0]).rstrip("\n")
						proc.wait()
					existsstr = "already exists, for file `"
					if myso:
						if re.search(existsstr, myso):
							# Already exists... Don't increment the count for this.
							pass
						elif myso[:44] == "install-info: warning: no info dir entry in ":
							# This info file doesn't contain a DIR-header: install-info produces this
							# (harmless) warning (the --quiet switch doesn't seem to work).
							# Don't increment the count for this.
							pass
						else:
							badcount += 1
							errmsg += myso + "\n"
					icount += 1

				if moved_old_dir and not os.path.exists(dir_file):
					# We didn't generate a new dir file, so put the old file
					# back where it was originally found.
					for ext in dir_extensions:
						try:
							os.rename(dir_file + ext + ".old", dir_file + ext)
						except EnvironmentError as e:
							if e.errno != errno.ENOENT:
								raise
							del e

				# Clean dir.old cruft so that they don't prevent
				# unmerge of otherwise empty directories.
				for ext in dir_extensions:
					try:
						os.unlink(dir_file + ext + ".old")
					except EnvironmentError as e:
						if e.errno != errno.ENOENT:
							raise
						del e

				#update mtime so we can potentially avoid regenerating.
				prev_mtimes[inforoot] = os.stat(inforoot)[stat.ST_MTIME]

			if badcount:
				out.eerror("Processed %d info files; %d errors." % \
					(icount, badcount))
				portage.util.writemsg_level(errmsg,
					level=logging.ERROR, noiselevel=-1)
			else:
				if icount > 0 and portage.util.noiselimit >= 0:
					out.einfo("Processed %d info files." % (icount,))
