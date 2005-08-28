#!/bin/bash
cd /usr/portage/
for x in `find -name '*.ebuild'`
do
	echo $x
	bn=${x##*/}
	dn=${x%/*}
	fn=.use-${bn/.ebuild/}
	myout=${dn}/${fn}

	#massive pipeline follows
	sed -e 's/^\([^#]*\)#.*$/\1/' -e '/^pkg_/q' $x | \
	grep -e 'use [[:alnum:]]*' | \
	grep -v DESCRIPTION | \
	sed -e 's/^.*use \([[:alnum:]]*\).*$/\1/' | \
	sed -e '/^$/d' | \
	sort | \
	uniq > $myout
	
done
