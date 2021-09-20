[![CI](https://github.com/gentoo/portage/actions/workflows/ci.yml/badge.svg)](https://github.com/gentoo/portage/actions/workflows/ci.yml)

About Portage
=============

Portage is a package management system based on ports collections. The
Package Manager Specification Project (PMS) standardises and documents
the behaviour of Portage so that ebuild repositories can be used by
other package managers.

Contributing
============

Contributions are always welcome! We've started using
[black](https://pypi.org/project/black/) to format the code base. Please make
sure you run it against any PR's prior to submitting (otherwise we'll probably
reject it).

There are [ways to
integrate](https://black.readthedocs.io/en/stable/integrations/editors.html)
black into your text editor and/or IDE.

You can also set up a git hook to check your commits, in case you don't want
editor integration. Something like this:

```sh
# .git/hooks/pre-commit (don't forget to chmod +x)

#!/bin/bash
black --check --diff .
```

To ignore commit 1bb64ff452 - which is a massive commit that simply formatted
the code base using black - you can do the following:

```sh
git config blame.ignoreRevsFile .gitignorerevs
```

Dependencies
============

Python and Bash should be the only hard dependencies. Python 3.6 is the
minimum supported version.

Native Extensions
=================

Portage includes some optional native extensions which can be built
in the source tree by running the following command:

    python setup.py build_ext --inplace --portage-ext-modules

The following setup.cfg settings can be used to enable building of
native extensions for all invocations of the build_ext command (the
build_ext command is invoked automatically by other build commands):

```
   [build_ext]
   portage_ext_modules=true
```

Currently, the native extensions only include libc bindings which are
used to validate LC_CTYPE and LC_COLLATE behavior for EAPI 6. If the
native extensions have not been built, then portage will use ctypes
instead.

Licensing and Legalese
=======================

Portage is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
version 2 as published by the Free Software Foundation.

Portage is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Portage; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
02110-1301, USA.


More information
================

- DEVELOPING contains some code guidelines.
- LICENSE contains the GNU General Public License version 2.
- NEWS contains new features/major bug fixes for each version.
- RELEASE NOTES contains mainly upgrade information for each version.
- TEST-NOTES contains Portage unit test information.


Links
=====

- Gentoo project page: https://wiki.gentoo.org/wiki/Project:Portage
- PMS: https://dev.gentoo.org/~ulm/pms/head/pms.html
- PMS git repo: https://gitweb.gentoo.org/proj/pms.git/
