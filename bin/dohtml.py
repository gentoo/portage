#!/usr/bin/python -b
# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

#
# Typical usage:
# dohtml -r docs/*
#  - put all files and directories in docs into /usr/share/doc/${PF}/html
# dohtml foo.html
#  - put foo.html into /usr/share/doc/${PF}/html
#
#
# Detailed usage:
# dohtml <list-of-files>
#  - will install the files in the list of files (space-separated list) into
#    /usr/share/doc/${PF}/html, provided the file ends in .css, .gif, .htm,
#    .html, .jpeg, .jpg, .js or .png.
# dohtml -r <list-of-files-and-directories>
#  - will do as 'dohtml', but recurse into all directories, as long as the
#    directory name is not CVS
# dohtml -A jpe,java [-r] <list-of-files[-and-directories]>
#  - will do as 'dohtml' but add .jpe,.java (default filter list is
#    added to your list)
# dohtml -a png,gif,html,htm [-r] <list-of-files[-and-directories]>
#  - will do as 'dohtml' but filter on .png,.gif,.html,.htm (default filter
#    list is ignored)
# dohtml -x CVS,SCCS,RCS -r <list-of-files-and-directories>
#  - will do as 'dohtml -r', but ignore directories named CVS, SCCS, RCS
#

import os as _os
import sys

from portage import _unicode_encode, _unicode_decode, os, shutil
from portage.util import normalize_path, writemsg

# Change back to original cwd _after_ all imports (bug #469338).
os.chdir(os.environ["__PORTAGE_HELPER_CWD"])

def dodir(path):
	try:
		os.makedirs(path, 0o755)
	except OSError:
		if not os.path.isdir(path):
			raise
		os.chmod(path, 0o755)

def dofile(src,dst):
	shutil.copy(src, dst)
	os.chmod(dst, 0o644)

def eqawarn(lines):
	cmd = "source '%s/isolated-functions.sh' ; " % \
		os.environ["PORTAGE_BIN_PATH"]
	for line in lines:
		cmd += "eqawarn \"%s\" ; " % line
	os.spawnlp(os.P_WAIT, "bash", "bash", "-c", cmd)

skipped_directories = []
skipped_files = []
warn_on_skipped_files = os.environ.get("PORTAGE_DOHTML_WARN_ON_SKIPPED_FILES") is not None
unwarned_skipped_extensions = os.environ.get("PORTAGE_DOHTML_UNWARNED_SKIPPED_EXTENSIONS", "").split()
unwarned_skipped_files = os.environ.get("PORTAGE_DOHTML_UNWARNED_SKIPPED_FILES", "").split()

def install(basename, dirname, options, prefix=""):
	fullpath = basename
	if prefix:
		fullpath = os.path.join(prefix, fullpath)
	if dirname:
		fullpath = os.path.join(dirname, fullpath)

	if options.DOCDESTTREE:
		desttree = options.DOCDESTTREE
	else:
		desttree = "html"

	destdir = os.path.join(options.ED, "usr", "share", "doc",
		options.PF.lstrip(os.sep), desttree.lstrip(os.sep),
		options.doc_prefix.lstrip(os.sep), prefix).rstrip(os.sep)

	if not os.path.exists(fullpath):
		sys.stderr.write("!!! dohtml: %s does not exist\n" % fullpath)
		return False
	elif os.path.isfile(fullpath):
		ext = os.path.splitext(basename)[1][1:]
		if ext in options.allowed_exts or basename in options.allowed_files:
			dodir(destdir)
			dofile(fullpath, os.path.join(destdir, basename))
		elif warn_on_skipped_files and ext not in unwarned_skipped_extensions and basename not in unwarned_skipped_files:
			skipped_files.append(fullpath)
	elif options.recurse and os.path.isdir(fullpath) and \
	     basename not in options.disallowed_dirs:
		for i in _os.listdir(_unicode_encode(fullpath)):
			try:
				i = _unicode_decode(i, errors='strict')
			except UnicodeDecodeError:
				writemsg('dohtml: argument is not encoded as UTF-8: %s\n' %
					_unicode_decode(i), noiselevel=-1)
				sys.exit(1)
			pfx = basename
			if prefix:
				pfx = os.path.join(prefix, pfx)
			install(i, dirname, options, pfx)
	elif not options.recurse and os.path.isdir(fullpath):
		global skipped_directories
		skipped_directories.append(fullpath)
		return False
	else:
		return False
	return True


class OptionsClass:
	def __init__(self):
		self.PF = ""
		self.ED = ""
		self.DOCDESTTREE = ""

		if "PF" in os.environ:
			self.PF = os.environ["PF"]
			if self.PF:
				self.PF = normalize_path(self.PF)
		if "force-prefix" not in os.environ.get("FEATURES", "").split() and \
			os.environ.get("EAPI", "0") in ("0", "1", "2"):
			self.ED = os.environ.get("D", "")
		else:
			self.ED = os.environ.get("ED", "")
		if self.ED:
			self.ED = normalize_path(self.ED)
		if "_E_DOCDESTTREE_" in os.environ:
			self.DOCDESTTREE = os.environ["_E_DOCDESTTREE_"]
			if self.DOCDESTTREE:
				self.DOCDESTTREE = normalize_path(self.DOCDESTTREE)

		self.allowed_exts = ['css', 'gif', 'htm', 'html', 'jpeg', 'jpg', 'js', 'png']
		if os.environ.get("EAPI", "0") in ("4-python", "5-progress"):
			self.allowed_exts += ['ico', 'svg', 'xhtml', 'xml']
		self.allowed_files = []
		self.disallowed_dirs = ['CVS']
		self.recurse = False
		self.verbose = False
		self.doc_prefix = ""

def print_help():
	opts = OptionsClass()

	print("dohtml [-a .foo,.bar] [-A .foo,.bar] [-f foo,bar] [-x foo,bar]")
	print("       [-r] [-V] <file> [file ...]")
	print()
	print(" -a   Set the list of allowed to those that are specified.")
	print("      Default:", ",".join(opts.allowed_exts))
	print(" -A   Extend the list of allowed file types.")
	print(" -f   Set list of allowed extensionless file names.")
	print(" -x   Set directories to be excluded from recursion.")
	print("      Default:", ",".join(opts.disallowed_dirs))
	print(" -p   Set a document prefix for installed files (empty by default).")
	print(" -r   Install files and directories recursively.")
	print(" -V   Be verbose.")
	print()

def parse_args():
	argv = sys.argv[:]

	# We can't trust that the filesystem encoding (locale dependent)
	# correctly matches the arguments, so use surrogateescape to
	# pass through the original argv bytes for Python 3.
	fs_encoding = sys.getfilesystemencoding()
	argv = [x.encode(fs_encoding, 'surrogateescape') for x in argv]

	for x, arg in enumerate(argv):
		try:
			argv[x] = _unicode_decode(arg, errors='strict')
		except UnicodeDecodeError:
			writemsg('dohtml: argument is not encoded as UTF-8: %s\n' %
				_unicode_decode(arg), noiselevel=-1)
			sys.exit(1)

	options = OptionsClass()
	args = []

	x = 1
	while x < len(argv):
		arg = argv[x]
		if arg in ["-h","-r","-V"]:
			if arg == "-h":
				print_help()
				sys.exit(0)
			elif arg == "-r":
				options.recurse = True
			elif arg == "-V":
				options.verbose = True
		elif argv[x] in ["-A","-a","-f","-x","-p"]:
			x += 1
			if x == len(argv):
				print_help()
				sys.exit(0)
			elif arg == "-p":
				options.doc_prefix = argv[x]
				if options.doc_prefix:
					options.doc_prefix = normalize_path(options.doc_prefix)
			else:
				values = argv[x].split(",")
				if arg == "-A":
					options.allowed_exts.extend(values)
				elif arg == "-a":
					options.allowed_exts = values
				elif arg == "-f":
					options.allowed_files = values
				elif arg == "-x":
					options.disallowed_dirs = values
		else:
			args.append(argv[x])
		x += 1

	return (options, args)

def main():

	(options, args) = parse_args()

	if options.verbose:
		print("Allowed extensions:", options.allowed_exts)
		print("Document prefix : '" + options.doc_prefix + "'")
		print("Allowed files :", options.allowed_files)

	success = False
	endswith_slash = (os.sep, os.sep + ".")

	for x in args:
		trailing_slash = x.endswith(endswith_slash)
		x = normalize_path(x)
		if trailing_slash:
			# Modify behavior of basename and dirname
			# as noted in bug #425214, causing foo/ to
			# behave similarly to the way that foo/*
			# behaves.
			x += os.sep
		basename = os.path.basename(x)
		dirname  = os.path.dirname(x)
		success |= install(basename, dirname, options)

	for x in skipped_directories:
		eqawarn(["QA Notice: dohtml on directory '%s' without recursion option" % x])
	for x in skipped_files:
		eqawarn(["dohtml: skipped file '%s'" % x])

	if success:
		retcode = 0
	else:
		retcode = 1

	sys.exit(retcode)

if __name__ == "__main__":
	main()
