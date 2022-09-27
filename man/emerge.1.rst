======
emerge
======

---------------------------------------------------------
The standard command-line interface to the Portage system
---------------------------------------------------------

:Authors:
    - Daniel Robbins <drobbins@gentoo.org>
    - Geert Bevin <gbevin@gentoo.org>
    - Achim Gottinger <achim@gentoo.org>
    - Nicholas Jones <carpaski@gentoo.org>
    - Phil Bordelon <phil@thenexusproject.org>
    - Mike Frysinger <vapier@gentoo.org>
    - Marius Mauch <genone@gentoo.org>
    - Jason Stubbs <jstubbs@gentoo.org>
    - Brian Harring <ferringb@gmail.com>
    - Zac Medico <zmedico@gentoo.org>
    - Arfrever Frehtes Taifersar Arahesis <arfrever@apache.org>
    - Oskari Pirhonen <xxc3ncoredxx@gmail.com>
:Date: 2022-09-26
:Copyright:
    Copyright 1999-2022 Gentoo Authors.  Distributed under the terms of the
    GNU General Public License v2
:Version: Portage VERSION
:Manual section: 1
:Manual group: Portage


Synopsis
========

| ``emerge`` [action_] [options_] [*atom* | *ebuild* | *file* | *@set* | *tbz2file*] ...
| ``emerge --sync`` [*repository* | *alias*] ...
| ``emerge --info`` [*atom*]
| ``emerge --search`` *search string*


Description
===========

``emerge`` is the definitive command-line interface to the Portage system and
which should be used in most situations.  The primary use case is for installing
new packages, updating existing ones, and uninstalling ones which are no longer
desired while automatically handling dependency resolution.  It is capable of
managing both source-based and binary packages and can even create distributable
binary packages.  ``emerge`` can also be used to update the *ebuild
repositories* which makes new and/or updated packages available to the user.


Atoms, ebuilds, files, sets, and .tbz2's
----------------------------------------

There are five ways to specify packages for installation: *atoms*, *ebuilds*,
already installed *files*, *sets*, and *tbz2files*.

atom
    An *atom* describes bounds on a package for installation (see
    ``ebuild``\ (5) for details on the syntax).  For example,
    ``>=dev-lang/python-2.2.1-r2`` matches the latest available version of
    Python which is newer than or equal to 2.2.1-r2.  Similarly,
    ``<dev-lang/python-2.0`` matches the latest available version of Python
    older 2.0.  An *atom* can also be constrained to match a specific *slot* by
    appending a colon and the desired *slot*. For example, ``x11-libs/qt:3``
    will match the newest QT library that occupies *slot* 3.

    .. NOTE::
       Many shells will need characters such as ``<`` and  ``=`` to be escaped.
       Using single or double quotes around the *atom* avoids the need for
       escaping them (and makes the command look cleaner).

ebuild
    An *ebuild* must be, at minimum, a valid Portage package directory name
    without the *category* or version number.  For example, ``portage`` or
    ``python``.  *Categories* and version numbers can be given for added
    precision.  For example, ``sys-apps/portage`` or ``=python-2.2.1-r2``.  The
    *ebuild* can also be a path to an actual file.  For example,
    ``/var/db/repos/gentoo/app-admin/python/python-2.2.1-r2.ebuild``.
    ``emerge`` ignores a trailing slash so that the shell's filename completion
    can be used.
    
    .. WARNING::
       The implementation of ``emerge /path/to/ebuild`` is broken and this
       syntax should not be used.

file
    A *file* must be a file or directory that has been installed by one or more
    packages.  Relative paths, if used, must begin with either ``./`` or
    ``../``.  If a directory is owned by multiple packages, all of them will be
    selected for installation (see the ``portageq owners`` command to
    query the owners of files or directories).

set
    A *set* is a convenient shorthand for a large group of packages and is
    generally used with ``--update``.  When *sets* are used as arguments to
    ``emerge`` they need to be prefixed with ``@`` in order to distinguish them
    from the other types of arguments.  ``--list-sets`` can be used to list the
    *sets* available on the system.

    There are currently six standard *sets* which are always available:
    ``selected-packages``, ``selected-sets``, ``selected``, ``system``,
    ``profile``, and ``world``.  ``selected-packages`` contains the user-\
    selected *world* packages that are listed in */var/lib/portage/world* and
    ``selected-sets`` contains the nested sets that may be listed in
    */var/lib/portage/world_sets*.  ``system`` and ``profile`` both refer to
    sets of packages that have been deemed necessary for proper system function
    (see ``portage``\ (5) for the differences between the two).  ``selected`` is
    a union of ``selected-packages`` and ``selected-sets``.  ``world`` is a
    union of ``selected``, ``system``, and ``profile``.  Other *sets* may exist
    depending on the current system configuration.  The default *set*
    configuration can be found in the */usr/share/portage/config/sets*
    directory and custom *sets* can be created in the */etc/portage/sets*
    directory (see ``portage``\ (5) for more information).

tbz2file
    A *tbz2file* must be a valid *binpkg* created with one of the following
    commands:

    - ``ebuild`` *package-version.ebuild* ``package``
    - ``emerge --buildpkg`` [*category/*]\ *package*
    - ``quickpkg`` [*category/*]\ *package*


.. _Action:

Actions
=======

No action
    When no action is explicitly given, the default action is to *merge* the
    specified packages along with any needed dependencies.  The arguments can be
    *atoms*, *ebuilds*, *files*, *sets*, or *tbz2files* as defined above.  The
    installed packages are then added to the *world* set so that they can be
    updated later.

    .. NOTE::
       The ``--usepkg`` option must be used when installing from a *tbz2*.

--check-news
    Scan each repository for relevant unread `GLEP 42`_ *news* items, and show how
    many are found.

--clean
    Clean the system by examining the installed packages and removing old
    packages.  This is done by separating each installed package by their
    *slot*.  ``--clean`` will remove all but the most recently installed version
    in each slot.  It should not remove any unslotted packages.

    .. NOTE::
       Most recently installed means newest *by install date*. This is not
       necessarily the newest *by version number*.

--config
    Run package-specific actions that are needed after the *emerge* process has
    completed.  This usually means setting up configuration files or other
    similar setup tasks that the user may wish to do.

--depclean, -c
    Clean the system by removing packages that are not required by any
    explicitly *merged* packages.  ``--depclean`` works by creating a full
    dependency tree from the packages currently in the *world* set and comparing
    it to the set of installed packages.  Any packages which are installed but
    not part of the dependency tree will be uninstalled.  Packages that are part
    of the *world* set will always be kept with potentially the exception of
    ones listed in *package.provided* (see ``portage``\ (5)).  See
    ``--with-bdeps`` for beahvior regarding build-time dependencies that are not
    strictly required and ``--noreplace`` for how to add packages to the *world*
    set manually.

    ``--depclean`` is essentially a dependency-aware version of ``--unmerge``.
    When given one or more *atoms* it will *unmerge* matched packages that have
    no reverse dependencies left.  Use the ``--verbose`` option to list reverse
    dependencies in the output.  ``--depclean`` may still break link level
    dependencies, especially if the ``--depclean-lib-check`` option is disabled.
    Tools such as ``revdep-rebuild``\ (1) can be used to detect this breakage.

    As a safety measure, ``--depclean`` will not remove any packages unless ALL
    required dependencies have been resolved.  This means running
    ``emerge --update --changed-use --deep @world`` will often be necessary
    before ``--depclean`` will succeed.

    .. WARNING::
       Inexperienced users should use ``--ask`` or ``--pretend`` in order to see
       a preview of what will be uninstalled.  Always study the list for
       mistakes to ensure no undesired packages get removed.

--deselect=< y | n >, -W
    Remove *atoms* / *sets* from the *world file*.  This is the default when no
    argument is given and is implied by uninstall actions such as
    ``--depclean``, ``--prune``, and ``--unmerge``.  Use ``--deselect=n`` to
    prevent the uninstall actions from removing *atoms* from the *world file*.

--help, -h
    Display a brief syntax overview for ``emerge``.

--info
    Dump information which helps developers when diagnosing and fixing bugs.
    Please include this output when creating a bug report.  Use ``--verbose``
    for expanded output.

--list-sets
    Display the list of available *sets*.

--metadata
    Transfer the pregenerated metadata cache from a repository's
    *metadata/md5-cache* to */var/cache/edb/dep* as is done at the end of
    ``emerge --sync`` when using rsync.  Portage uses this cache for pre-parsed
    lookups of package data.  No cache is populated for repositories that don't
    distribute pregenerated metadata.  The metadata cache can be generated for
    these repositories with ``--regen``.  This action is unnecessary in versions
    of Portage >=2.1.5 unless ``metadata-transfer`` is set in *FEATURES* in
    *make.conf*.

--prune, -P
    Remove all but the highest installed version of a package from the system.
    Use ``--verbose`` to show reverse dependencies or ``--nodeps`` to ignore all
    dependencies.

    .. WARNING::
       This action can remove packages from your world file!  Check the output
       of the next ``--depclean`` carefully before it proceeds.

--regen
    Check and update the dependency cache of all the ebuilds in the repository.
    The cache speeds up searching and building dependency trees.  Regeneration
    can be done in parallel using ``--jobs`` and ``--load-average``.  See
    ``egencache``\ (1) to generate a distributable cache usable by others.

    This action is not recommended for rsync users since rsync updates the cache
    using server-side caches.  Rsync users should just use ``emerge --sync`` for
    this.  If you don't know the difference between an "rsync user" and some
    other user, then you're an "rsync user" ;)

--resume, -r
    Resume the morst recent *merge* list that has been aborted due to an error.
    The original options and arguments are re-used, and new ones can be provided
    as well.  Providing new *atoms* or *sets* is an error.  The resume list will
    be stored until it has been successfully completed or a new aborted *merge*
    list replaces it.  The resume history can store two lists, and  after one
    list has been completed, ``--resume`` can be run again to resume an older
    list.

    This action will only return an error on failure.  If there is nothing to
    do, ``emerge`` will exit with an appropriate message and a success exit
    code.

    Resume lists are stored in */var/cache/edb/mtimedb* and can be manually
    discarded using ``emaint --fix cleanresume``.  See ``emaint``\ (1) for more
    details.

--search, -s
    Search for matches of the given string with package names in the ebuild
    repository.  A simple case-insensitive search is used by default, but
    regular expressions can also be used by prefixing the string with ``%``
    (this prefix can be omitted if the ``--regex-search-auto`` option is
    enabled, which it is by default).  To include the category in the search,
    prefix the string with ``@``.

    For example, to search for packages whose name contains "office"::
        
        emerge --search "office"

    To search for packages whose name starts with "kde"::
        
        emerge --search "%^kde"

    To search for packages whose name ends with "gcc"::
        
        emerge --search "%gcc$"

    To search for packages in the "dev-java" category which end with "jdk"::
        
        emerge --search  "%@^dev-java.*jdk"

--searchdesc, -S
    Like ``--search``, but match the string against the package descriptions as
    well as the names.

--sync
    Update repositories that have their *auto-sync*, *sync-type*, and *sync-uri*
    attributes set in *repos.conf*.  A list of repositories or aliases can be
    given to update them regardless of *auto-sync*.  See ``portage``\ (5) for
    more info about these (and other) attributes.  The *PORTAGE_SYNC_STALE*
    environment variable can be used to configure warnings that are shown when
    repositories have not been updated recently.

    .. WARNING::
       The ``--sync`` action will revert any local changes, such as adding new
       files or modifying existing ones, in repositories that are updated with
       rsync.

    .. NOTE::
       ``emerge --sync`` is a compatibility command.  The sync operations
       themselves are performed with the newer *emaint sync* module which
       provides more functionality and greater flexibility.  See ``emaint``\ (1)
       for more information on using the module.

       The *emerge-webrsync* program will download the entire Gentoo ebuild
       repository as a tarball which is much faster than ``emerge --sync`` for
       the initial sync.

--unmerge, -C
    Remove all matching packages after a counter controlled by the *CLEAN_DELAY*
    environment variable.

    .. WARNING::
       This action does NOT check dependencies and can remove important packages
       that are necessary for the system to function properly!  To account for
       dependencies when removing packages, use ``--depclean`` or ``--prune``.

--rage-clean
    Same as ``--unmerge``, but act as if *CLEAN_DELAY* was set to ``0``.

--version, -V
    Display the version number of *emerge*.


Options
=======

--accept-properties=ACCEPT_PROPERTIES
              This option temporarily overrides the ACCEPT_PROPERTIES variable. The ACCEPT_PROPERTIES variable is incremental, which means that the specified setting is appended to the existing value from your configuration. The  spe‐
              cial  -*  token can be used to discard the existing configuration value and start fresh. See the MASKED PACKAGES section and make.conf(5) for more information about ACCEPT_PROPERTIES. A typical usage example for this op‐
              tion would be to use --accept-properties=-interactive to temporarily mask interactive packages. With default configuration, this would result in an effective ACCEPT_PROPERTIES value of "* -interactive".

--accept-restrict=ACCEPT_RESTRICT

--alert [ y | n ], -A

--alphabetical

--ask [ y | n ], -a

--ask-enter-invalid

--autounmask [ y | n ]

--autounmask-backtrack < y | n >

--autounmask-continue [ y | n ]

--autounmask-only [ y | n ]

--autounmask-unrestricted-atoms [ y | n ]

--autounmask-keep-keywords [ y | n ]

--autounmask-keep-masks [ y | n ]

--autounmask-license < y | n >

--autounmask-use < y | n >

--autounmask-write [ y | n ]

--backtrack=COUNT

--binpkg-changed-deps [ y | n ]

--binpkg-respect-use [ y | n ]

--buildpkg [ y | n ], -b

--buildpkg-exclude ATOMS

--buildpkgonly, -B

--changed-deps [ y | n ]

--changed-deps-report [ y | n ]

--changed-slot [ y | n ]

--changed-use, -U

--color < y | n >

--columns

--complete-graph [ y | n ]

--complete-graph-if-new-use < y | n >

--complete-graph-if-new-ver < y | n >

--config-root=DIR

--debug, -d

--deep [DEPTH], -D

--depclean-lib-check [ y | n ]

--digest

--dynamic-deps < y | n >

--emptytree, -e

--exclude, -X ATOMS

--fail-clean [ y | n ]

--fetchonly, -f

--fetch-all-uri, -F

--fuzzy-search [ y | n ]

--getbinpkg [ y | n ], -g

--getbinpkgonly [ y | n ], -G

--ignore-default-opts

--ignore-built-slot-operator-deps < y | n >

--ignore-soname-deps < y | n >

--ignore-world [ y | n ]

--implicit-system-deps < y | n >

-j [JOBS], --jobs[=JOBS]

--keep-going [ y | n ]

-l [LOAD], --load-average[=LOAD]

--misspell-suggestions < y | n >

--newrepo

--newuse, -N

--noconfmem

--nodeps, -O

--noreplace, -n

--nospinner

--usepkg-exclude ATOMS

--rebuild-exclude ATOMS

--rebuild-ignore ATOMS

--regex-search-auto < y | n >

--oneshot, -1

--onlydeps, -o

--onlydeps-with-rdeps < y | n >

--package-moves [ y | n ]

--pkg-format

--prefix=DIR

--pretend, -p

--quickpkg-direct < y | n >

--quickpkg-direct-root=DIR

--quiet [ y | n ], -q

--quiet-build [ y | n ]

--quiet-fail [ y | n ]

--quiet-repo-display

--quiet-unmerge-warn

--read-news [ y | n ]

--rebuild-if-new-slot [ y | n ]

--rebuild-if-new-rev [ y | n ]

--rebuild-if-new-ver [ y | n ]

--rebuild-if-unbuilt [ y | n ]

--rebuilt-binaries [ y | n ]

--rebuilt-binaries-timestamp=TIMESTAMP

--reinstall changed-use

--reinstall-atoms ATOMS

--root=DIR

--sysroot=DIR

--root-deps[=rdeps]

--search-index < y | n >

--search-similarity PERCENTAGE

--select [ y | n ], -w

--selective [ y | n ]

--skipfirst

--sync-submodule <glsa|news|profiles>

--tree, -t

--unordered-display

--update, -u

--use-ebuild-visibility [ y | n ]

--useoldpkg-atoms ATOMS

--usepkg [ y | n ], -k

--usepkgonly [ y | n ], -K

--usepkg-exclude-live [ y | n ]

--verbose [ y | n ], -v

--verbose-conflicts

--verbose-slot-rebuilds [ y | n ]

--with-bdeps < y | n >

--with-bdeps-auto < y | n >

--with-test-deps [ y | n ]


Output
======


Masked Packages
===============


Configuration File Protection
=============================

Configuration file update tools
-------------------------------


Reporting Bugs
==============

Please report bugs via https://bugs.gentoo.org/ and include the output of
``emerge --info`` in the report.


Files
=====

/etc/portage/make.conf

/etc/portage/repos.conf/*

/etc/portage/sets/*

/usr/share/portage/config/sets/*

/var/cache/edb/mtimedb

/var/lib/portage/world

/var/lib/portage/world_sets


Environment Variables
=====================

CLEAN_DELAY

PORTAGE_SYNC_STALE


See Also
========

``ebuild``\ (1)
``ebuild``\ (5)
``egencache``\ (1)
``emaint``\ (1)
``make.conf``\ (5)
``portage``\ (5)
``quickpkg``\ (1)
``revdep-rebuild``\ (1)

``emerge-webrsync --help``

``portageq --help``

.. _GLEP 42:

https://www.gentoo.org/glep/glep-0042.html


TODO
====

- More relevant example atoms in the atom description
- Document what the files and env vars are used for
- Use case for ``emerge --clean``?
- Adding one of the additional arguments listed above will give you more
  specific help information on that subject.

  - Original manpage had this, is it still valid?? Didn't work when I tried it.
