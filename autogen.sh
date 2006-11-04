#!/bin/sh

die() {
	echo "!!! $*" > /dev/stderr
	exit -1
}

#autoheader || { echo "failed autoheader"; exit 1; };
aclocal-1.8 || die "failed aclocal"
[ "`type -t glibtoolize`" == "file" ] && alias libtoolize=glibtoolize
libtoolize --automake -c -f || die "failed libtoolize"
autoconf || die "failed autoconf"
touch ChangeLog 
automake-1.8 -a -c || die "failed automake"

if [ -x ./test.sh ] ; then
	exec ./test.sh "$@"
fi
echo "finished"
