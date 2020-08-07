#!/usr/bin/python -b

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

import re
import sys

implicit_pattern = re.compile(r"([^:]*):(\d+): warning: implicit declaration "
                              + "of function [`']([^']*)'")
pointer_pattern = (
    r"([^:]*):(\d+): warning: "
    + r"("
    +  r"(assignment"
    +  r"|initialization"
    +  r"|return"
    +  r"|passing arg \d+ of `[^']*'"
    +  r"|passing arg \d+ of pointer to function"
    +  r") makes pointer from integer without a cast"
    + r"|"
    + r"cast to pointer from integer of different size)")

unicode_quote_open = '\u2018'
unicode_quote_close = '\u2019'
def write(msg):
    sys.stdout.buffer.write(msg.encode('utf_8', 'backslashreplace'))

pointer_pattern = re.compile(pointer_pattern)

last_implicit_filename = ""
last_implicit_linenum = -1
last_implicit_func = ""

while True:
    line = sys.stdin.buffer.readline().decode('utf_8', 'replace')
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
