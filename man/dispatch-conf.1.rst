=============
dispatch-conf
=============

-------------------------------------------------------------
Sanely update configuration files after emerging new packages
-------------------------------------------------------------

:Authors:
    - Jeremy Wohl
    - Karl Trygve Kalleberg <karltk@gentoo.org>
    - Mike Frysinger <vapier@gentoo.org>
    - Grant Goodyear <g2boojum@gentoo.org>
    - Oskari Pirhonen <xxc3ncoredxx@gmail.com>
:Date: 2022-08-24
:Copyright:
    Copyright 1999-2022 Gentoo Authors.  Distributed under the terms of the
    GNU General Public License v2
:Version: Portage VERSION
:Manual section: 1
:Manual group: Portage


Synopsis
========

``dispatch-conf``


Description
===========

``dispatch-conf`` is designed to be run after emerging new packages in order to
see if there are any updates to the configuration files.  If a new configuration
file would overwrite an existing one, *dispatch-conf* will prompt the user on
how to resolve the conflict.  Advantages of *dispatch-conf* include: easy
rollback (changes to config files are stored using either ``patch``\ (1) files
or ``rcs``\ (1)) and automatic updates to config files that the user has never
modified (or that differ from the current version only in CVS cruft or
whitespace).

*dispatch-conf* will check all the directories found in the *CONFIG_PROTECT*
variable.  All config files found in the *CONFIG_PROTECT_MASK* variable will be
updated automatically.  See ``make.conf``\ (5) for more information.


Options
=======

None.


Usage
=====

``dispatch-conf`` must be run as root since the config files to be replaced are
generally owned by root.  Before running ``dispatch-conf`` for the first time,
the settings in */etc/dispatch-conf.conf* should be edited and the archive
directory specified therein created.  All changes to config files will be saved
to the archive directory.

When *dispatch-conf* finds a config file requiring an update, the user is
presented with a menu containing the following options for how to proceed:

u
    Update (replace) the current config file with the new config file and
    continue.

z
    Zap (delete) the new config file and continue.

n
    Skip to the next config file, leaving both the original config file and any
    *CONFIG_PROTECT*-ed files.

e
    Edit the new config file, using the editor defined in *EDITOR*.

m
    Interactively merge the current and new config files.

l
    Look at the differences between the pre-merged and merged config files.

t
    Toggle between the merged and pre-merged config files (which one will be
    installed with the ``u`` command).

h
    Display a help screen.

q
    Quit *dispatch-conf*.


File Modes
==========

.. WARNING::
    When */etc/dispatch-conf.conf* is configured to use ``rcs``\ (1), the read
    and execute permissions of archived files may be inherited from the first
    check-in of a working file as documented in the ``ci``\ (1) man page.  This
    means that even if the permissions of the working file have changed, the
    older permissions of the first check-in may be inherited.  As mentioned in
    the ``ci``\ (1) man page, users can control access to *rcs* files by setting
    the permissions of the directory containing the files.


conf-update Hooks
=================

*dispatch-conf* will run hooks found in */etc/portage/conf-update.d*.  The first
argument of the hook is either ``pre-session``, ``post-session``,
``pre-update``, or ``post-update``.  In the case of ``pre-`` / ``post-update``
events, a second argument containing the path to the config file is provided.


Reporting Bugs
==============

Please report bugs via https://bugs.gentoo.org/


Files
=====

/etc/dispatch-conf.conf
    Configuration settings for *dispatch-conf* are stored here.


See Also
========

``ci``\ (1)
``etc-update``\ (1)
``make.conf``\ (5)
``rcs``\ (1)


TODO
====

- Document *dispatch-conf.conf*
