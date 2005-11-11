#!/bin/sh

autoheader || { echo "failed autoheader"; exit 1; };
aclocal-1.8 || { echo "failed aclocal"; exit 1; };
libtoolize --automake -c -f || { echo "failed libtoolize"; exit 1; }
autoconf || { echo "failed autoconf"; exit 1; }
touch ChangeLog 
automake-1.8 -a -c || { "echo failed automake"; exit 1; }

if [ -x ./test.sh ] ; then
	exec ./test.sh "$@"
fi
echo "finished"
