======
emaint
======

-----------------------------------------------------------------------
Perform package management-related system health checks and maintenance
-----------------------------------------------------------------------

:Authors:
    - Pavel Kazakov <nullishzero@gentoo.org>
    - Mike Frysinger <vapier@gentoo.org>
    - Brian Dolbec <dolsen@gentoo.org>
    - Oskari Pirhonen <xxc3ncoredxx@gmail.com>
:Date: 2022-09-09
:Copyright:
    Copyright 1999-2022 Gentoo Authors.  Distributed under the terms of the
    GNU General Public License v2
:Version: Portage VERSION
:Manual section: 1
:Manual group: Portage


Synopsis
========

``emaint`` [options_] *command*


Description
===========

``emaint`` provides a command line interface to package management health checks
and maintenance.


Options
=======

Common options
--------------

These options are supported by most commands.  More specifically, all but:
``logs`` (no ``-f``),
``sync`` (no ``-c`` or ``-f``).

-c, --check
    Check for any problems that may exist.

-f, --fix
    Fix any problems that may exist.

--version
    Show the version number and exit.


logs options
------------

These options are specific to the ``logs`` command.

-C, --clean
    Clean the logs from *PORTAGE_LOGDIR*.

-p, --pretend
    Set pretend mode (same as ``-c``, ``--check``) for use with
    ``-C``, ``--clean``.

-t NUM, --time NUM
    Change the minimum age of the logs to be listed or deleted to *NUM* days.


merges options
--------------

These options are specific to the ``merges`` command.

-P, --purge
    Remove the list of previous failed *merges*.

    .. WARNING::
       Only use if you plan to manually fix the packages or don't want them
       reinstalled.

-y, --yes
    Accept all prompts given by *emerge*.


sync options
------------

These options are specific to the ``sync`` command.

-a, --auto
    Sync repositories which have their *auto-sync* setting set to
    ``yes`` / ``true``.

-A, --allrepos
    Sync all repositories which have a *sync-uri* specified.

-r REPO, --repo REPO
    Sync the specified repository.

--sync-submodule <glsa|news|profiles>
    Restrict sync to the specified submodule(s).  This option may be specified
    multiple times in order to sync multiple submodules.  This option currently
    has no effect for sync protocols other than *rsync*.


Commands
========

all
    Run all commands that accept the given option.

binhost
    Generate a metadata index for binary packages located in *PKGDIR* for
    download by remote clients.  See the *PORTAGE_BINHOST* documentation in
    ``make.conf``\ (5) for more information.

cleanconfmem
    Discard no longer installed config tracker entries.

cleanresume
    Discard merge lists saved for the ``emerge``\ (1) ``--resume`` action.

logs
    Clean up old logs from the *PORTAGE_LOGDIR* directory using the
    *PORTAGE_LOGDIR_CLEAN* command.  See ``make.conf``\ (5) for more
    information on this as well as the ``clean-logs`` option in *FEATURES* to do
    this automatically.

merges
    Scan for failed package *merges* and attempt to fix the failed packages.

movebin
    Perform *package move* updates for binary packages in *PKGDIR*.

moveinst
    Perform *package move* updates for installed packages.

sync
    Sync the specified repositories.

world
    Fix problems in the *world* file.


Reporting Bugs
==============

Please report bugs via https://bugs.gentoo.org/


Files
=====

/var/lib/portage/config
    Contains the paths and *md5sums* for all the tracked config files.

/var/lib/portage/failed-merges
    Contains the packages and timestamps of any failed *merges* being cleaned
    from the system to be *re-merged*.

/var/lib/portage/world
    Contains a list of all user-specified packages.


See Also
========

``emerge``\ (1)
``make.conf``\ (5)
``portage``\ (5)
