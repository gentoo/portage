#! /usr/bin/env python
# $Header: /var/cvsroot/gentoo-src/portage/src/bsd-flags/setup.py,v 1.1.2.1 2005/02/06 12:56:40 carpaski Exp $

from os import chdir, stat
from distutils.core import setup, Extension

setup (# Distribution meta-data
        name = "bsd-chflags",
        version = "0.1",
        description = "",
        author = "Stephen Bennett",
        author_email = "spb@gentoo.org",
       	license = "",
        long_description = \
         '''''',
        ext_modules = [ Extension(
                            "chflags",
                            ["chflags.c"],
                            libraries=[],
                        ) 
                      ],
        url = "",
      )

