#!/usr/bin/env sh

die() {
	echo "!!! $*" > /dev/stderr
	exit -1
}

#autoheader || { echo "failed autoheader"; exit 1; };
aclocal || die "failed aclocal"
[ "`type -t glibtoolize`" = "file" ] && alias libtoolize=glibtoolize
libtoolize --automake -c -f || die "failed libtoolize"
autoconf || die "failed autoconf"
touch ChangeLog 
automake -a -c || die "failed automake"

if [ -x ./test.sh ] ; then
	exec ./test.sh "$@"
fi
echo "finished"
