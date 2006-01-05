#!/bin/bash
# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/bin/md5check.sh,v 1.2 2004/10/04 13:56:50 vapier Exp $

# pipe in the data.

sort -u -                    > md5check.tmp
grep '^Extra'   md5check.tmp > md5check.tmp.extra
grep '^Missing' md5check.tmp > md5check.tmp.missing
grep '^Coll'    md5check.tmp > md5check.tmp.colliding

sed -i "
s:^Col:\nCol:
s:,:\n  :g
s: of :\n  :g
s: and :\n  :g" md5check.tmp.colliding
sed -i "s/^[^ ]\+ md5sum: \(.*\) in \(.*\)$/  \2: \1/g" md5check.tmp.missing
sed -i "s/^[^ ]\+ md5sum: \(.*\) in \(.*\)$/  \2: \1/g" md5check.tmp.extra

#echo "Colliding files:" > md5check.colliding
#sort -u md5check.tmp.colliding >> md5check.colliding
cp md5check.tmp.colliding md5check.colliding

echo "Missing from digest:" > md5check.missing
sort -u md5check.tmp.missing >> md5check.missing

echo "Extra files in digest:" > md5check.extra
sort -u md5check.tmp.extra >> md5check.extra

rm md5check.tmp*
