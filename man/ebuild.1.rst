======
ebuild
======

-------------------------------------------
Low level interface to the Portage system
-------------------------------------------

:Authors:
    - Achim Gottinger <achim@gentoo.org>
    - Daniel Robbins <drobbins@gentoo.org>
    - Nicholas Jones <carpaski@gentoo.org>
    - Mike Frysinger <vapier@gentoo.org>
    - Oskari Pirhonen <xxc3ncoredxx@gmail.com>
:Date: 2022-09-05
:Copyright:
    Copyright 1999-2022 Gentoo Authors.  Distributed under the terms of the
    GNU General Public License v2
:Version: Portage VERSION
:Manual section: 1
:Manual group: Portage


Synopsis
========

``ebuild`` [options_] *file* *command* ...


Description
===========

``ebuild`` is a direct interface into the Portage system and enables manually
performing specific actions (or groups of actions) define in a given ebuild.
Examples include: fetching distfiles, unpacking sources, compiling sources, and
creating a binary package from the image.


Options
=======

--debug
    Run ``bash`` with the ``-x`` option, causing it to output verbose debugging
    information to *stdout*.

--color < y | n >
    Enable or disable color output.  This option will override *NOCOLOR* (see
    ``make.conf``\ (5)) and can also be used to force color output when *stdout*
    is not a *tty* (color is disabled by default when *stdout* is not a *tty*).

--force
    When used together with the ``digest`` or ``manifest`` commands, this option
    forces regeneration of digests for all distfiles associated with the current
    ebuild.  Any distfiles that do not already exist in *DISTDIR* will be
    fetched automatically.

--ignore-default-opts
    Do not use the *EBUILD_DEFAULT_OPTS* environment variable.

--skip-manifest
    Skip all manifest checks.


File
====

A path to a (valid) ebuild.


Commands
========

By default, Portage will execute all the functions, in order, up to (and
including) the one specified on the command line, but skipping over the
functions that have already been executed in a previous ``ebuild`` run.  For
example, specifying only the ``compile`` command will trigger the pre-requisite
phases (such as ``setup`` and ``unpack``) unless they have already been
successfully completed.  Specifying ``clean`` first will ensure all previous
phases are run again.  To only run the specified command, add ``noauto`` to the
*FEATURES* environment variable.

help
    Show a condensed form of this *man* page along with a lot of package-\
    specific information.

setup
    Perform package-specific setup actions by running the ``pkg_setup`` function
    defined in the ebuild and any exotic system checks.

clean
    Clean the temporary build directory that Portage has created for this
    particular ebuild.  The build directory normally contains the extracted
    source files as well as a possible install image (all the files that will be
    *merged* into the local filesystem or stored in a package).  The location of
    the build directory is set by the *PORTAGE_TMPDIR* variable.  Run ``emerge
    --info`` for information on the variable's value.  See ``make.conf``\ (5)
    for overriding the variable.

    .. NOTE::
       Portage cleans up almost everything after a successful *merge* unless
       ``noclean`` is set in *FEATURES*.  Using this option will consume large
       amounts of space very quickly.  It is not recommended to have this
       feature on unless you have a need for the sources post-merge.  Otherwise
       they can be manually cleaned with ``rm -rf /var/tmp/portage`` (assuming
       the default build directory).

fetch
    Check if all the sources specified in *SRC_URI* are available in *DISTDIR*
    (see ``make.conf``\ (5) for more information) and have a valid checksum.  If
    any sources are missing, an attempt is made to download them from the
    locations specified in *SRC_URI*.  If multiple download locations are listed
    for a particular file, Portage pings each location to determine the closest
    one (may not currently be true).  The mirrors given in *GENTOO_MIRRORS* are
    always tried first.

    If the current or just downloaded sources's checksums don't match their
    recorded values, a warning is printed and *ebuild* exits with an error code
    of ``1``.

digest
    Equivalent to the ``manifest`` command.

manifest
    Update the Manifest file for the package.  This calculates checksums for all
    the files found in the same directory as the ebuild, the recursive contents
    of the *files* subdirectory, and all of the files listed in *SRC_URI*.  See
    the documentation for the ``assume-digests`` option for *FEATURES* for more
    info about the behavior of this command.  See the ``--force`` option to
    prevent digests from being assumed.

unpack
    Extract the sources into the build directory by running the ``src_unpack``
    function from the ebuild.  If no ``src_unpack`` is defined, a default
    function is used that extracts all the files specified in *SRC_URI*.

prepare
    Prepare the extracted sources for compilation by running the ``src_prepare``
    function from the ebuild.  This includes applying patches specified in the
    ebuild and user patches found in */etc/portage/patches*.

configure
    Configure the prepared sources by running the ``src_configure`` function
    from the ebuild.

compile
    Compile the configured sources by running the ``src_compile`` function from
    the ebuild.

test
    Run package-specific test cases by running the ``src_test`` function from
    the ebuild to verify that everything was built properly.

install
    Install the package to the temporary install directory by running the
    ``src_install`` function from the ebuild.

preinst
    Perform package-specific actions that are needed before the package can be
    installed into the live filesystem by running the ``pkg_preinst`` function
    from the ebuild.

instprep
    Perform additional post-install/pre-merge preparation inside the temporary
    install directory.  This is intended to be called after building a binary
    package but before executing ``preinst``.

postinst
    Run package-specific actions that are needed after the package has been
    installed into the live filesystem by running the ``pkg_postinst`` function
    from the ebuild.  Helpful messages are usually shown here.

qmerge
    Install all the files in the temporary installation directory into the live
    filesystem.

    The process is as follows:

    - the ``pkg_preinst`` function (if specified) is run
    - the files are *merged* into the live filesystem
    - the installed files's checksums are recorded
    - the ``pkg_postinst`` function (if specified) is run

merge
    Normally to *merge* an ebuild, you need to *fetch*, *unpack*, *prepare*,
    *configure*, *compile*, *install* and *qmerge*.  To simply *merge*, this
    command will perform the required steps, stopping if a particular step does
    not succeed.

unmerge
    First, run the ``pkg_prerm`` function from the ebuild (if specified).  Then,
    remove all files from the live filesystem that have valid checksums and
    *mtime* in the package *CONTENTS* file.  Any empty directories are
    recursively removed.  Finally, run ``pkg_postrm`` function from the ebuild
    (if specified).  It is safe to *merge* a new version of a package before
    *unmerging* the old one (this is the recommended package upgrade method).

prerm
    Run package-specific actions that are needed before the package is removed
    from the filesystem by running the ``pkg_prerm`` function from the ebuild.

postrm
    Run package-specific actions that are needed after the package is removed
    from the filesystem by running the ``pkg_postrm`` function from the ebuild.

config
    Run package-specific actions that are need after the *emerge* process has
    completed by running the ``pkg_config`` function from the ebuild.  This
    usually means setting up configuration files or other similar setup tasks
    that the user may wish to do.

package
    Similar to the ``merge`` command except that after *fetching*, *unpacking*,
    *preparing*, *configuring*, *compiling*, and *installing*, create a
    *.gpkg.tar* or *.tbz2* binary package tarball is and store it in *PKGDIR*
    (see ``make.conf``\ (5)).

rpm
    Build a RedHat *RPM* package from the files in the temporary install
    directory.  The ebuild's dependency information is currently not recorded in
    the *RPM* file.


Reporting Bugs
==============

Please report bugs via https://bugs.gentoo.org/


Files
=====

/etc/portage/make.conf
    Contains variables for the build-process and overwrites the ones found in
    *make.globals*.

/etc/portage/color.map
    Contains variables customizing colors.


Environment Variables
=====================

EBUILD_DEFAULT_OPTS
    Set of default options used for ``ebuild``.

FEATURES
    Controls whether Portage features are enabled or disabled.
    See ``make.conf``\ (5).

NOCOLOR
    Enables or disables color output.


See Also
========

``color.map``\ (5)
``ebuild``\ (5)
``emerge``\ (1)
``make.conf``\ (5)


TODO
====

- Flesh out some of the more "bare" commands?

  - Maybe add info about paths again?
  - Info about default versions?
