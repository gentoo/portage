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
import re
import sys

implicit_pattern = re.compile("([^:]*):(\d+): warning: implicit declaration "
                              + "of function [`']([^']*)'")
pointer_pattern = re.compile(
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
last_implicit_filename = ""
last_implicit_linenum = -1
last_implicit_func = ""

while True:
    line = sys.stdin.readline()
    if line == '':
        break
    # translate unicode open/close quotes to ascii ones
    line = line.replace("\xE2\x80\x98", "`").replace("\xE2\x80\x99", "'")
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
                print "Function `%s' implicitly converted to pointer at " \
                      "%s:%d" % (last_implicit_func, last_implicit_filename,
                                 last_implicit_linenum)
