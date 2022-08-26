==========
etc-update
==========

---------------------------------
handle configuration file updates
---------------------------------

:Authors:
    - Jochem Kossen
    - Leo Lipelis
    - Karl Trygve Kalleberg <karltk@gentoo.org>
    - Mike Frysinger <vapier@gentoo.org>
    - Oskari Pirhonen <xxc3ncoredxx@gmail.com>
:Date: 2022-08-25
:Copyright:
    Copyright 1999-2022 Gentoo Authors.  Distributed under the terms of the
    GNU General Public License v2
:Version: Portage VERSION
:Manual section: 1
:Manual group: Portage


Synopsis
========

``etc-update`` [options_] [``--automode`` <*mode*>] [*paths to scan*]


Description
===========

``etc-update`` is designed to be run after emerging new packages in order to see
if there are any updates to the configuration files.  If a new configuration
file would overwrite an existing one, *etc-update* will prompt the user on how
to resolve the conflict.

*etc-update* will check all the paths specified on the command line.  If no
paths are given, then the *CONFIG_PROTECT* variable will be used.  All config
files found in the *CONFIG_PROTECT_MASK* variable will be updated automatically.
See ``make.conf``\ (5) for more information.

*etc-update* respects the normal *PORTAGE_CONFIGROOT* and *EROOT* variables for
finding the aforementioned *CONFIG_PROTECT\** variables.


Options
=======

-d, --debug
    Run with shell tracing enabled.

-h, --help
    Surprisingly, show the help output.

-p, --preen
    Automerge trivial changes only and quit.

-v, --verbose
    Show settings and important decision info while running.

--automode <mode>
    Select one of the automatic merge modes.  Valid modes are: ``-3`` ``-5``
    ``-7`` ``-9``.  See the ``--help`` text for more details.


Reporting Bugs
==============

Please report bugs via https://bugs.gentoo.org/


Files
=====

/etc/etc-update.conf
    Configuration settings for *etc-update* are stored here.


See Also
========

``dispatch-conf``\ (1)
``make.conf``\ (5)


TODO
====

- Document the modes
- Add warning/note about deprecation in favor of ``dispatch-conf``\ (1)
