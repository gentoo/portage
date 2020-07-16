#!/usr/bin/python -b
# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os
import sys

from portage.util import apply_recursive_permissions

# Change back to original cwd _after_ all imports (bug #469338).
os.chdir(os.environ["__PORTAGE_HELPER_CWD"])

def main(files):

	# We can't trust that the filesystem encoding (locale dependent)
	# correctly matches the arguments, so use surrogateescape to
	# pass through the original argv bytes for Python 3.
	fs_encoding = sys.getfilesystemencoding()
	files = [x.encode(fs_encoding, 'surrogateescape') for x in files]

	for filename in files:
		# Emulate 'chmod -fR a+rX,u+w,g-w,o-w' with minimal chmod calls.
		apply_recursive_permissions(filename, filemode=0o644,
			filemask=0o022, dirmode=0o755, dirmask=0o022)

	return os.EX_OK

if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
