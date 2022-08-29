========
quickpkg
========

-----------------------
Create Portage packages
-----------------------

:Authors:
    - Terry Chan (original author)
    - Mike Frysinger <vapier@gentoo.org> (revamped version)
    - Oskari Pirhonen <xxc3ncoredxx@gmail.com>
:Date: 2022-08-28
:Copyright:
    Copyright 1999-2022 Gentoo Authors.  Distributed under the terms of the
    GNU General Public License v2
:Version: Portage VERSION
:Manual section: 1
:Manual group: Portage


Synopsis
========

``quickpkg`` [options_] <*package or package-set*> ...


Description
===========

``quickpkg`` is used to quickly create a binary package for Portage (hence the
name) by using the files already on your filesystem.  This package then can be
*emerged* on any system.  The freshly created package is stored in *PKGDIR*.
The default path is */var/cache/binpkgs*.

The upside to this is that there is no waiting for the *unpack*, *prepare*,
*configure*, *compile*, and *install* phases before the package is ready for
use.  The downside is that the package will contain the files from your
filesystem as they appear at the time of running ``quickpkg`` -- including any
local modifications made since the first install!

See ``emerge``\ (1) for the syntax for *emerging* binary packages.


Options
=======

--ignore-default-opts
    Causes the *QUICKPKG_DEFAULT_OPTS* environment variable to be ignored.

--include-config < y | n >
    Include all files protected by *CONFIG_PROTECT* (as a security precaution,
    default is *n*).

--include-unmodified-config < y | n >
    Include files protected by *CONFIG_PROTECT* that have not been modified
    since installation (as a security precaution, default is *n*).

--umask=UMASK
    The *umask* used during package creation (default is *0077*).

<package or package-set>
    The packages to create binary packages for.  These can be given in a few
    ways: the full path to the installed entry in the *virtual database*
    (*/var/db/pkg/<category>/<package>-<version>*), a Portage *depend atom*, or
    a Portage *package set*.

    The syntax for specifying *atoms* and *sets* is the same as what is used for
    ``emerge``\ (1).  See ``ebuild``\ (5) for how to specify an *atom*.


Reporting Bugs
==============

Please report bugs via https://bugs.gentoo.org/


Files
=====

/etc/portage/make.conf
       The environment variables are defined here.


Environment Variables
=====================

PKGDIR
    Gives the path to save created packages in.  Defaults to
    */var/cache/binpkgs*.

QUICKPKG_DEFAULT_OPTS
    Set of default options used for ``quickpkg``.


Examples
========

Create a package by specifying the full *VDB* path::
    
    quickpkg /var/db/pkg/dev-python/pyogg-1.1

Create a package by specifying only the package name::
    
    quickpkg planeshift

Create a package by specifying a full *atom*::
    
    quickpkg =apache-1.3.27-r1
    quickpkg =net-www/apache-2*

Create packages by specifying a *set*::
    
    quickpkg @system


See Also
========

``ebuild``\ (5)
``emerge``\ (1)
``make.conf``\ (5)
