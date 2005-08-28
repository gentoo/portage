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
# Indent:  indent -kr -i2 -ts2 -sob -l80 -ss -bs -psl
#
# $Header: /var/cvsroot/gentoo-src/portage/src/sandbox-1.1/Attic/Makefile,v 1.7.2.2 2004/11/29 08:41:28 carpaski Exp $

CC ?= gcc
LD ?= ld
CFLAGS = 
ARCH_CFLAGS =
OBJ_CFLAGS = -D_GNU_SOURCE -DPIC -fPIC -D_REENTRANT
LIBS =
LDFLAGS =
DESTDIR =

HAVE_64BIT_ARCH =

ifneq ($(HAVE_64BIT_ARCH),)
	TARGETS = libsandbox.so libsandbox32.so sandbox
	ARCH_CFLAGS += -m64
	OBJ_CFLAGS += -DSB_HAVE_64BIT_ARCH
else
	TARGETS = libsandbox.so sandbox
endif

all:	$(TARGETS)

sandbox: sandbox.o sandbox_futils.o getcwd.c
	$(CC) $(CFLAGS) $(ARCH_CFLAGS) $(OBJ_CFLAGS) -Wall $^ -ldl -lc -o $@

sandbox.o: sandbox.c sandbox.h
	$(CC) $(CFLAGS) $(ARCH_CFLAGS) $(OBJ_CFLAGS) -Wall -c sandbox.c -o $@

sandbox_futils.o: localdecls.h sandbox_futils.c sandbox.h
	$(CC) $(CFLAGS) $(ARCH_CFLAGS) $(OBJ_CFLAGS) -Wall -c sandbox_futils.c -o $@

libsandbox.so: libsandbox.o sandbox_futils.o
	$(CC) $^ -shared $(ARCH_CFLAGS) -fPIC -ldl -lc -nostdlib -lgcc -o $@

libsandbox.o: localdecls.h libsandbox.c canonicalize.c getcwd.c
	$(CC) $(CFLAGS) $(ARCH_CFLAGS) $(OBJ_CFLAGS) -Wall -c libsandbox.c

sandbox_futils32.o: sandbox_futils.c sandbox.h
	$(CC) $(CFLAGS) -m32 $(OBJ_CFLAGS) -Wall -c sandbox_futils.c -o $@

libsandbox32.so: libsandbox32.o sandbox_futils32.o
	$(CC) $^ -shared -m32 -fPIC -ldl -lc -nostdlib -lgcc -o $@

libsandbox32.o: libsandbox.c localdecls.h canonicalize.c getcwd.c
	$(CC) $(CFLAGS) -m32 $(OBJ_CFLAGS) -Wall -c libsandbox.c -o $@

localdecls.h: create-localdecls libctest.c
	./create-localdecls


install: all
	install -d -m 0755 $(DESTDIR)/lib
	$(if $(HAVE_64BIT_ARCH),install -d -m 0755 $(DESTDIR)/lib32)
	install -d -m 0755 $(DESTDIR)/usr/lib/portage/bin
	install -d -m 0755 $(DESTDIR)/usr/lib/portage/lib
	install -m 0755 libsandbox.so $(DESTDIR)/lib
	$(if $(HAVE_64BIT_ARCH),install -m 0755 libsandbox32.so $(DESTDIR)/lib32/libsandbox.so)
	install -m 0755 sandbox $(DESTDIR)/usr/lib/portage/bin
	install -m 0644 sandbox.bashrc $(DESTDIR)/usr/lib/portage/lib


clean:
	rm -f $(TARGETS)
	rm -f *.o *~ core
	rm -f localdecls.h


# vim:expandtab noai:cindent ai
