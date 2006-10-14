#! /usr/bin/env python
# $Id$

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

