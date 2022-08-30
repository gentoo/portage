==========
glsa-check
==========

----------------------------------------
Tool to locally monitor and manage GLSAs
----------------------------------------

:Authors:
    - Oskari Pirhonen <xxc3ncoredxx@gmail.com> (manpage only)
:Date: 2022-08-29
:Copyright:
    Copyright 1999-2022 Gentoo Authors.  Distributed under the terms of the
    GNU General Public License v2
:Version: Portage VERSION
:Manual section: 1
:Manual group: Portage


Synopsis
========

``glsa-check`` [options_] [*glsa-id* | *all* | *affected*]


Description
===========

``glsa-check`` is used to locally monitor and manage Gentoo Linux Security
Advisories.  In order for *glsa-check* to be effective, a local repository
containing GLSA metadata is required.


Options
=======

-c, --cve
    Show CVE IDs in listing mode.

-d, --dump, --print
    Show all information about the GLSA(s) or set.

-f, --fix
    (experimental) Attempt to remediate the system based on the instructions
    given in the GLSA(s) or set.  This will only upgrade (when an upgrade path
    exists) or remove packages.

-h, --help 
    Show this help message.

-i, --inject
    Inject the given GLSA(s) into the *glsa_injected* file.

-l, --list
    List a summary for the given GLSA(s) or set and whether they affect the
    system.

-m, --mail
    Send a mail with the given GLSAs to the administrator.

-n, --nocolor
    Remove colors from the output.

-p, --pretend
    Show the necessary steps to remediate the system.

-q, --quiet
    Be less verbose and do not send empty mail.

-r, --reverse
    List GLSAs in reverse order

-t, --test
    Test if this system is affected by the GLSA(s) or set and output the GLSA
    ID(s).

-v, --verbose
    Be more verbose.

-V, --version
    Show information about *glsa-check*.


Exit Status
===========

0
    Success

1
    Syntax or usage error

2
    Missing permissions, solution, etc

6
    System is affected by some GLSAs


Reporting Bugs
==============

Please report bugs via https://bugs.gentoo.org/


Files
=====

/var/lib/portage/glsa_injected
    List of GLSA ids that have been injected and will never show up as
    *affected* on the system.  The file must contain one GLSA ID
    (e.g. ``200804-02``) per line.


Examples
========

Test the system against all GLSAs in the repository::
    
    glsa-check -t all

Test the system against a specific GLSA (201801-01)::
    
    glsa-check -t 201801-01


See Also
========

https://security.gentoo.org
