# Copyright (C) 2001 Geert Bevin, Uwyn, http://www.uwyn.com
# Distributed under the terms of the GNU General Public License, v2 or later 
# Author : Geert Bevin <gbevin@uwyn.com>
#
# Modified 15 Apr 2002 Jon Nelson <jnelson@gentoo.org>
#  Clean up Makefile somewhat, and use make's implicit rules
#
# Modified 19 Aug 2002; Martin Schlemmer <azarah@gentoo.org>
#  Major rewrite to support new stuff
#
# $Header: /var/cvsroot/gentoo-src/portage/src/sandbox-dev/Attic/Makefile,v 1.3 2002/12/16 22:28:05 jrray Exp $

CC = gcc
LD = ld
CFLAGS =
OBJ_DEFINES = -D_GNU_SOURCE -DPIC -fPIC -D_REENTRANT
LIBS =
LDFLAGS =
DESTDIR =

TARGETS = libsandbox.so sandbox

all:	$(TARGETS)

sandbox: sandbox.o sandbox_futils.o
	$(CC) $^ -ldl -lc -o $@

sandbox.o: sandbox.c sandbox.h
	$(CC) $(CFLAGS) -Wall -c sandbox.c

sandbox_futils.o: sandbox_futils.c sandbox.h
	$(CC) $(CFLAGS) -Wall -c $(OBJ_DEFINES) sandbox_futils.c

libsandbox.so: libsandbox.o sandbox_futils.o canonicalize.o
	$(LD) $^ -shared -fPIC -ldl -lc -lpthread -o $@

libsandbox.o: libsandbox.c localdecls.h
	$(CC) $(CFLAGS) -Wall -c $(OBJ_DEFINES) libsandbox.c

canonicalize.o: canonicalize.c
	$(CC) $(CFLAGS) -Wall -c $(OBJ_DEFINES) canonicalize.c

localdecls.h: create-localdecls libctest.c
	./create-localdecls


install: all
	install -d -m 0755 $(DESTDIR)/lib
	install -d -m 0755 $(DESTDIR)/usr/lib/portage/bin
	install -d -m 0755 $(DESTDIR)/usr/lib/portage/lib
	install -m 0755 libsandbox.so $(DESTDIR)/lib
	install -m 0755 sandbox $(DESTDIR)/usr/lib/portage/bin
	install -m 0644 sandbox.bashrc $(DESTDIR)/usr/lib/portage/lib


clean:
	rm -f $(TARGETS)
	rm -f *.o *~ core
	rm -f localdecls.h


# vim:expandtab noai:cindent ai
