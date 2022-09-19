=========
color.map
=========

---------------------------------
Custom color settings for Portage
---------------------------------

:Authors:
    - Arfrever Frehtes Taifersar Arahesis <arfrever@apache.org>
    - Oskari Pirhonen <xxc3ncoredxx@gmail.com>
:Date: 2022-09-18
:Copyright:
    Copyright 1999-2022 Gentoo Authors.  Distributed under the terms of the
    GNU General Public License v2
:Version: Portage VERSION
:Manual section: 5
:Manual group: Portage


Description
===========

The *color.map* file located in the */etc/portage* directory contains variables
to define the color classes used by Portage for output.  Portage checks this
file when choosing the output color and falls back to internal defaults if no
definition for a color class is found.


Syntax
======

::
    
    CLASS = "[attributes]"

*[attributes]* is a space-separate list of attributes_ or a string with custom
ANSI color codes.  Lines beginning with ``#`` can be used for comments.


Color Classes
=============

These are the different configurable color classes that Portage uses along with
their internal default values.

BAD = *"red"*
    The color used for "bad" messages.

BRACKET = *"blue"*
    The color used for brackets.

ERR = *"red"*
    The color used for "error" messages.

GOOD = *"green"*
    The color used for "good" messages.

HILITE = *"teal"*
    The color used for highlighted words.

INFO = *"darkgreen"*
    The color used for "info" messages.

LOG = *"green"*
    The color used for "log" messages.

NORMAL = *"normal"*
    The color used for normal messages.

QAWARN = *"brown"*
    The color used for QA warnings.

WARN = *"yellow"*
    The color used for other warnings.

INFORM = *"darkgreen"*
    The color used for informational messages.

UNMERGE_WARN = *"red"*
    The color used for *unmerge* warnings.

SECURITY_WARN = *"red"*
    The color used for security warnings.

MERGE_LIST_PROGRESS = *"yellow"*
    The color used for numbers in the *emerge* progress indicator.

PKG_BLOCKER = *"red"*
    The color used for unsatisfied *blockers*.

PKG_BLOCKER_SATISFIED = *"teal"*
    The color used for satisfied *blockers*.

PKG_MERGE = *"darkgreen"*
    The color used for packages that are planned for *merge*.

PKG_MERGE_SYSTEM = *"darkgreen"*
    The color used for *@system* packages that are planned for *merge*.

PKG_MERGE_WORLD = *"green"*
    The color used for *@world* packages that are planned for *merge*.

PKG_BINARY_MERGE = *"purple"*
    The color used for packages that are planned for *merge* using a binary
    package.

PKG_BINARY_MERGE_SYSTEM = *"purple"*
    The color used for *@system* packages that are planned for *merge* using a
    binary package.

PKG_BINARY_MERGE_WORLD = *"fuchsia"*
    The color used for *@world* packages that are planned for *merge* using a
    binary package.

PKG_UNINSTALL = *"red"*
    The color used for packages that are planned for *unmerge* in order to
    resolve conflicts.

PKG_NOMERGE = *"teal"*
    The color used for packages that are not planned for *merge*.

PKG_NOMERGE_SYSTEM = *"teal"*
    The color used for *@system* packages that are not planned for *merge*.

PKG_NOMERGE_WORLD = *"blue"*
    The color used for *@world* packages that are not planned for *merge*.

PROMPT_CHOICE_DEFAULT = *"green"*
    The color used for the default choice when prompted.

PROMPT_CHOICE_OTHER = *"red"*
    The color used for the non-default choice when prompted.


Attributes
==========

Portage understands the following set of attributes.

.. NOTE::
    ``darkyellow`` and ``brown`` may be rendered as the same colors.  Same with
    ``darkteal`` and ``turquoise``.  Some consoles or terminals may only provide
    one of the two names, but Portage treats them both the same regardless.

    Additionally, not all consoles or terminals may necessarily support all of
    the different attributes.

..

+-------------------+-------------------+-------------------+
| Foreground colors | Background colors | Other attributes  |
+===================+===================+===================+
| black             | bg_black          | normal            |
+-------------------+-------------------+-------------------+
| darkgray          |                   | no-attr           |
+-------------------+-------------------+-------------------+
| darkred           | bg_darkred        | reset             |
+-------------------+-------------------+-------------------+
| red               |                   | bold              |
+-------------------+-------------------+-------------------+
| darkgreen         | bg_darkgreen      | faint             |
+-------------------+-------------------+-------------------+
| green             |                   | standout          |
+-------------------+-------------------+-------------------+
| brown             | bg_brown          | no-standout       |
+-------------------+-------------------+-------------------+
| yellow            |                   | underline         |
+-------------------+-------------------+-------------------+
| darkyellow        | bg_darkyellow     | no-underline      |
+-------------------+-------------------+-------------------+
| darkblue          | bg_darkblue       | blink             |
+-------------------+-------------------+-------------------+
| blue              |                   | no-blink          |
+-------------------+-------------------+-------------------+
| purple            | bg_purple         | overline          |
+-------------------+-------------------+-------------------+
| fuchsia           |                   | no-overline       |
+-------------------+-------------------+-------------------+
| teal              | bg_teal           | reverse           |
+-------------------+-------------------+-------------------+
| darkteal          |                   | no-reverse        |
+-------------------+-------------------+-------------------+
| turquoise         |                   | invisible         |
+-------------------+-------------------+-------------------+
| lightgray         | bg_lightgray      |                   |
+-------------------+-------------------+-------------------+
| white             |                   |                   |
+-------------------+-------------------+-------------------+
|                   | bg_default        |                   |
+-------------------+-------------------+-------------------+


Reporting Bugs
==============

Please report bugs via https://bugs.gentoo.org/


Files
=====

/etc/portage/color.map
    Contains variables used for colorizing Portage output.


See Also
========

``console_codes``\ (4)
``emerge``\ (1)
``portage``\ (5)


TODO
====

- Syntax in proper BNF? Or at least pseudo-BNF?
- Cool examples?
- Table gets cut at some kind of page boundary by *man*?
