===========
emirrordist
===========

---------------------------------
Fetch tool for distfile mirroring
---------------------------------

:Authors:
    - Zac Medico <zmedico@gentoo.org>
    - Arfrever Frehtes Taifersar Arahesis <arfrever@apache.org>
    - Oskari Pirhonen <xxc3ncoredxx@gmail.com>
:Date: 2022-09-12
:Copyright:
    Copyright 1999-2022 Gentoo Authors.  Distributed under the terms of the
    GNU General Public License v2
:Version: Portage VERSION
:Manual section: 1
:Manual group: Portage


Synopsis
========

``emirrordist`` [options_] <*action*>


Options
=======

--dry-run
    Perform a trial run with no changes made (typically combined with
    ``-v`` or ``-vv``).

-v, --verbose
    Display extra information on *stderr*.  Can be given multiple times for
    increased verbosity.

--ignore-default-opts
    Do not use the *EMIRRORDIST_DEFAULT_OPTS* environment variable.

--distfiles=DIR
    *Distfiles* directory to use (required).

-j JOBS, --jobs=JOBS
    Number of concurrent jobs to run.

-l LOAD, --load-average=LOAD
    Maximum load average where spawning new jobs is allowed.

--tries=TRIES
    Maximum number of tries per file (``0`` is unlimited, default is ``10``).

--repo=REPO
    Name of the repository to operate on.

--config-root=DIR
    Location of Portage config files.

--repositories-configuration=REPOSITORIES_CONFIGURATION
    Override repository configuration.  The format is the same as for
    *repos.conf* (see ``portage``\ (5)).

--strict-manifests=<y|n>
    Override the ``strict`` option in *FEATURES*.

--failure-log=FILE
    File used for logging fetch failures.  Opened in *append* mode and uses
    tab-delimited output.

--success-log=FILE
    File used for logging fetch successes.  Opened in *append* mode and uses
    tab-delimited output.

--scheduled-deletion-log=FILE
    File used for logging scheduled deletions.  Overwritten each time and uses
    tab-delimited output.

--content-db=FILE
    Database used for pairing content digests with *distfile* names (required
    for content-hash layout).

--delete
    Delete unused *distfiles*.

--deletion-db=FILE
    Database used for tracking the lifetimes of files scheduled for delayed
    deletion.

--deletion-delay=SECONDS
    How many seconds to delay the deletion of unused *distfiles* for.

--temp-dir=DIR
    Temporary directory used for downloads.

--mirror-overrides=FILE
    File with a list of *mirror* overrides.

--mirror-skip=MIRROR_SKIP
    Comma separated list of *mirrors* to skip when fetching.

--restrict-mirror-exemptions=RESTRICT_MIRROR_EXEMPTIONS
    Comma separated list of *mirrors* to ignore ``RESTRICT="mirror"`` on (see
    ``ebuild``\ (5)).

--verify-existing-digest
    Use the *digest* to verify the integrity of existing *distfiles*.

--distfiles-local=DIR
    Local directory used to store *distfiles* in.

--distfiles-db=FILE
    Database used for tracking which *ebuild* a *distfile* belongs to.

--recycle-dir=DIR
    Directory for extended retention of files that are removed from the main
    *distfile* directory with ``--delete``.  These files can be be used instead
    of re-fetching them if they are needed again.

--recycle-db=FILE
    Database used for tracking the lifetimes of files in the recycle directory.

--recycle-deletion-delay=SECONDS
    How many seconds to delay the deletion of unused files in the recycle directory for
    (default is ``5184000``, or better known as 60 days).

--fetch-log-dir=DIR
    Directory for individual fetch logs.

--whitelist-from=FILE
    File containing a list of files to whitelist.  One entry per line.  Lines
    beginning with ``#`` are ignored and can be used for comments.  This option
    can be given multiple times to use multiple whitelists.

--symlinks
    Use symbolic links instead of hard links when linking *distfiles* from other
    layouts to the primary layout (default is hard links).

--layout-conf=FILE
    Specify an alternate mirror *layout.conf* file to use in order to select the
    desired *distfile* layout.  The default is to use the *layout.conf* from the
    directory given with ``--distfiles`` (if found).  Otherwise a flat layout is
    assumed.


Actions
=======

-h, --help
    Show a help message and exit.

--version
    Display Portage version and exit.

--mirror
    Mirror *distfiles* for the selected repository.


Reporting Bugs
==============

Please report bugs via https://bugs.gentoo.org/


Files
=====

/etc/portage/make.conf
    Contains Portage environment variables.


Environment Variables
=====================

EMIRRORDIST_DEFAULT_OPTS
    Set of default options used for ``emirrordist``.


See Also
========

``ebuild``\ (5)
``make.conf``\ (5)
``portage``\ (5)


Thanks
======

Special thanks to Brian Harring, the author of the *mirror-dist* program from
which *emirrordist* is based on.


TODO
====

- Create a ``Description`` section
- Sort options_ nicer
- Whitelist from what?
