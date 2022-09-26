====
xpak
====

---------------------------------------------------------
The old XPAK data format used for Portage binary packages
---------------------------------------------------------

:Authors:
    - Lars Hartmann <lars@chaotika.org>
    - Mike Frysinger <vapier@gentoo.org>
    - Oskari Pirhonen <xxc3ncoredxx@gmail.com>
:Date: 2022-09-25
:Copyright:
    Copyright 1999-2022 Gentoo Authors.  Distributed under the terms of the
    GNU General Public License v2
:Version: Portage VERSION
:Manual section: 5
:Manual group: Portage


Description
===========

Old-style Portage binary packages consist of a *bzip2*-compressed tarball of
package files and an appended *xpak*.  The *xpak* is a bespoke archive format
designed to hold package build-time information such as the *ebuild* it was
built from, the list of *USE* flags used, environment variables, *CFLAGS*, etc.
Basically, everything that would be needed to rebuild a new copy of the package
within the tarball (excluding the sources themselves).

.. IMPORTANT::
   Depending on when you're reading this, the *xpak* format has been superceded
   (or is in the process of being superceded) by the shiny new *gpkg* binary
   package format, and they are incompatible BY DESIGN.  Differences between the
   two formats are beyond the scope of this document, but see `GLEP 78`_ for the
   details and rationale behind the new format.


XPAK Format
===========

The following data types will be used in this document:

integer
    All *integers* are unsigned 32 bit big-endian.

string
    All *strings* are ASCII encoded and are NOT null-terminated.

value
    All *xpak* entries's *values* are stored as *strings*.

Miscellaneous punctuation is just for a visual aid and not part of the data
itself.


Overview
--------

binpkg (.tbz2)
    ::
        
                |<-- xpak_off -->|
        tarball |      xpak      | xpak_off | "STOP"

xpak
    ::
        
        "XPAKPACK" | index_len | data_len | index | data | "XPAKSTOP"

index
    ::
        
        index1 | index2 | ... | index(N-1) | indexN

indexN
    ::
        
                 |<-- name_len -->|
        name_len |      name      | dataN_off | dataN_len

data
    ::
        
        |<--                   data_len                  -->|
        |<--         dataN_off         -->|<-- dataN_len -->|
        | data1 | data2 | ... | data(N-1) |      dataN      |


The gory details
----------------

Opening a *binpkg* with a hex editor will show a tarball of files followed by a
binary blob.  This blob consists of the *xpak* itself and some metadata: the
*xpak_off*, and the *string* ``STOP``.

::
    
            |<-- xpak_off -->|
    tarball |      xpak      | xpak_off | "STOP"

*xpak_off* is an *integer* with the offset of the start of the *xpak* from the
location of the offset when going backwards in the file.  It's a rather poorly-\
named field, but it makes more sense if "offset" is mentally translated to
"length".

This is what the *xpak* looks like::
    
    "XPAKPACK" | index_len | data_len | index | data | "XPAKSTOP"

It begins with the *string* ``XPAKPACK``.  Following this are two *integers*:
*index_len* which is the length of the *index* block and *data_len* which is the
length of the *data* block. Then there's the *index* and *data* blocks
themselves. Finally, the end of the *xpack* is marked with the *string*
``XPAKSTOP``.

Because the *data* block is nothing more than just different bits of data
concatenated together, an *index* is needed in order to split it back up into
the individual components.  This is found, unsurprisingly, in the *index*
block::
    
    index1 | index2 | ... | index(N-1) | indexN

This block is just a list of *index* elements::
    
             |<-- name_len -->|
    name_len |      name      | dataN_off | dataN_len

Each element begins with an *integer*: *name_len*.  After this is a *string* of
*name_len* characters which gives the name of the element.  After the name are
two more *integers*: *dataN_off* which is the offset into the *data* block
corresponding to the Nth element and *dataN_len* which is the length of the
data.

The *data* block itself is quite simple, being nothing more than a collection
of data snippets that is *data_len* bytes long::
    
    |<--                   data_len                  -->|
    |<--         dataN_off         -->|<-- dataN_len -->|
    | data1 | data2 | ... | data(N-1) |      dataN      |

Accessing a specific element consists of finding the corresponding *index*
element and reading the data offset and length fields contained in it.  To get
the Nth element, read *dataN_len* bytes starting from *dataN_off* bytes into the
block.


Reporting Bugs
==============

Please report bugs via https://bugs.gentoo.org/


Example
=======

Consider the following *xpak* with two *data* chunks.  The first is called
"fil1" and contains "ddDddDdd".  The second is called "fil2" and contains
"jjJjjJjj".

Hexdump::
    
    00  58 50 41 4b 50 41 43 4b  00 00 00 20 00 00 00 10  |XPAKPACK... ....|
    10  00 00 00 04 66 69 6c 31  00 00 00 00 00 00 00 08  |....fil1........|
    20  00 00 00 04 66 69 6c 32  00 00 00 08 00 00 00 08  |....fil2........|
    30  64 64 44 64 64 44 64 64  6a 6a 4a 6a 6a 4a 6a 6a  |ddDddDddjjJjjJjj|
    40  58 50 41 4b 53 54 4f 50                           |XPAKSTOP|

No *xpak_off* or ``STOP`` is included since it's just a raw *xpak*.

Here's a breakdown of the different bits:

::
    
       |      "XPAKPACK"       || index_len | data_len  |
    00  58 50 41 4b 50 41 43 4b  00 00 00 20 00 00 00 10  |XPAKPACK... ....|

The *index_len* in this case is 32 bytes and the *data_len* is 16 bytes.

::
    
       | name_len  |   name    || data1_off | data1_len |
    10  00 00 00 04 66 69 6c 31  00 00 00 00 00 00 00 08  |....fil1........|

This is the first *index* element.  *name_len* gives the length of the name as
4 bytes, and the next 4 bytes are the name itself ("fil1").  The *data1_off* is
0 and the *data1_len* is 8 which means that the data is the first 8 bytes at the
very front of the *data* block.

::
    
       | name_len  |   name    || data2_off | data2_len |
    20  00 00 00 04 66 69 6c 32  00 00 00 08 00 00 00 08  |....fil2........|

This is the second *index* element.  It's very similar to the first.  Note that
the *data2_off* is 8 and the *data2_len* is 8 which means the data is the next 8
bytes, starting at the 9th byte of the *data* block.

::
    
       |<--                 data_len                 -->|
       |         data1         ||         data2         |
    30  64 64 44 64 64 44 64 64  6a 6a 4a 6a 6a 4a 6a 6a  |ddDddDddjjJjjJjj|

This is the start of the *data* block, which is 32 bytes after the start of the
*index* block (it also happens to be the entire block in this example).  The
first 8 bytes correspond with *data1* and the second 8 bytes with *data2*.
Together, the lengths add up to 16 bytes which is the same as what's given in
*data_len* above.

::
    
       |      "XPAKSTOP"       |
    40  58 50 41 4b 53 54 4f 50                           |XPAKSTOP|

Last, but not least, is ``XPAKSTOP`` which marks the end of the *xpak*.


See Also
========

``quickpkg``\ (1)
``qxpak``\ (1) (from *app-portage/portage-utils*)

.. _GLEP 78:

https://gentoo.org/glep/glep-0078.html
