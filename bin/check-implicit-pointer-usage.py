#!/usr/bin/python

# Ripped from HP and updated from Debian
# Update by Gentoo to support unicode output

#
# Copyright (c) 2004 Hewlett-Packard Development Company, L.P.
#	David Mosberger <davidm@hpl.hp.com>
#
# Scan standard input for GCC warning messages that are likely to
# source of real 64-bit problems.  In particular, see whether there
# are any implicitly declared functions whose return values are later
# interpreted as pointers.  Those are almost guaranteed to cause
# crashes.
#

from __future__ import print_function

import re
import sys

implicit_pattern = re.compile("([^:]*):(\d+): warning: implicit declaration "
                              + "of function [`']([^']*)'")
pointer_pattern = (
    "([^:]*):(\d+): warning: "
    + "("
    +  "(assignment"
    +  "|initialization"
    +  "|return"
    +  "|passing arg \d+ of `[^']*'"
    +  "|passing arg \d+ of pointer to function"
    +  ") makes pointer from integer without a cast"
    + "|"
    + "cast to pointer from integer of different size)")

if sys.hexversion < 0x3000000:
    # Use encoded byte strings in python-2.x, since the python ebuilds are
    # known to remove the encodings module when USE=build is enabled (thus
    # disabling unicode decoding/encoding). The portage module has a
    # workaround for this, but currently we don't import that here since we
    # don't want to trigger potential sandbox violations due to stale pyc
    # files for the portage module.
    unicode_quote_open = '\xE2\x80\x98'
    unicode_quote_close = '\xE2\x80\x99'
    def write(msg):
        sys.stdout.write(msg)
else:
    unicode_quote_open = '\u2018'
    unicode_quote_close = '\u2019'
    def write(msg):
        sys.stdout.buffer.write(msg.encode('utf_8', 'backslashreplace'))

pointer_pattern = re.compile(pointer_pattern)

last_implicit_filename = ""
last_implicit_linenum = -1
last_implicit_func = ""

while True:
    if sys.hexversion >= 0x3000000:
        line = sys.stdin.buffer.readline().decode('utf_8', 'replace')
    else:
        line = sys.stdin.readline()
    if not line:
        break
    # translate unicode open/close quotes to ascii ones
    line = line.replace(unicode_quote_open, "`")
    line = line.replace(unicode_quote_close, "'")
    m = implicit_pattern.match(line)
    if m:
        last_implicit_filename = m.group(1)
        last_implicit_linenum = int(m.group(2))
        last_implicit_func = m.group(3)
    else:
        m = pointer_pattern.match(line)
        if m:
            pointer_filename = m.group(1)
            pointer_linenum = int(m.group(2))
            if (last_implicit_filename == pointer_filename
                and last_implicit_linenum == pointer_linenum):
                write("Function `%s' implicitly converted to pointer at " \
                      "%s:%d\n" % (last_implicit_func,
                                   last_implicit_filename,
                                   last_implicit_linenum))
