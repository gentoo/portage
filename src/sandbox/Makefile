# Copyright (C) 2001 Geert Bevin, Uwyn, http://www.uwyn.com
# Distributed under the terms of the GNU General Public License, v2 or later 
# Author : Geert Bevin <gbevin@uwyn.com>
#
# Modified 15 Apr 2002 Jon Nelson <jnelson@gentoo.org>
#  Clean up Makefile somewhat, and use make's implicit rules
#
# $Header: /var/cvsroot/gentoo-src/portage/src/sandbox/Attic/Makefile,v 1.5 2002/08/05 16:44:34 drobbins Exp $

.SUFFIXES:
.SUFFIXES: .c .o .so
.PRECIOUS: %.o

%.so: LIBS=-ldl
%.so: LDFLAGS=--shared
%.so: %.o 
	$(CC) $(CFLAGS) $(CPPFLAGS) $< -o $@ $(LIBS) $(LDFLAGS)
        
CC = gcc
CFLAGS = -Wall -O0 -fPIC
LIBS =
LDFLAGS =

TARGETS = sandbox libsandbox.so

all:	$(TARGETS)

clean:
	rm -f $(TARGETS)
	rm -f *.o *~
