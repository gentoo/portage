#!/bin/bash

if [ -z "$1" ] ; then
	echo "Usage: $0 <version>"
	exit 1
fi

find man -name '*.eclass.5' > man-page-list
tar -jcf portage-manpages-${1}.tar.bz2 --files-from man-page-list
echo "Packed away $(wc -l man-page-list | cut -f1 -d' ') manpages"
rm -f man-page-list

ls -l portage-manpages-${1}.tar.bz2
