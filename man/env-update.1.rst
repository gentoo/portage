==========
env-update
==========

-----------------------------------------
update environment settings automatically
-----------------------------------------

:Authors:
    - Daniel Robbins <drobbins@gentoo.org>
    - Oskari Pirhonen <xxc3ncoredxx@gmail.com>
:Date: 2022-08-26
:Copyright:
    Copyright 1999-2022 Gentoo Authors.  Distributed under the terms of the
    GNU General Public License v2
:Version: Portage VERSION
:Manual section: 1
:Manual group: Portage


Synopsis
========

``env-update`` [options_]


Description
===========

*env-update* reads the files in */etc/env.d* and automatically generates
*/etc/profile.env* and */etc/ld.so.conf*.  Then ``ldconfig``\ (8) is run to
update */etc/ld.so.cache*.  ``env-update`` is run by ``emerge``\ (1)
automatically after each package merge.

Making manual changes to */etc/env.d* requires running ``env-update`` for the
changes to take effect immediately.

.. NOTE::
    This only affects new processes.  ``source /etc/profile`` needs to be run
    in any active shells as well for the changes to take effect there.


Options
=======

--no-ldconfig
    Do not run ``ldconfig``\ (8) (and thus skip rebuilding the *ld.so.cache*,
    etc...).


Reporting Bugs
==============

Please report bugs via https://bugs.gentoo.org/


See Also
========

``emerge``\ (1)
``ldconfig``\ (8)
