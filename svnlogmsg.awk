#!/usr/bin/env bash

# bla bla
# probably can be done much better, but I got tired of copy 'n' paste
# from mutt into a commit message ...

# just one big reminder for myself: svn log and svn merge/diff theirs -r
# argument are *NOT* semantically the same!  The former is some
# inclusive thing, where the later is exclusive on the start range.
# e.g.: svn log make.conf.arm.diff -r4689:4690
# results in the log for revision 4689, but
# svn diff make.conf.arm.diff -r4689:4690
# results in an empty set

[[ -z $1 ]] && exit -1

if [[ ${1/:/} != $1 ]] ; then
	t1=${1%:*} ; t1=${t1#-r} ; t1=${t1#r}
	t2=${1#*:}
	# see above
	t1=$((t1 + 1))
	r=${t1}:${t2}
else
	r=${1#-r} ; r=${r#r}
fi

svn log ../../trunk -r$r | awk -v revs=$1 '
BEGIN {
	term = 0
	print "<html>"
	print "Merged from trunk " revs
	print "<table border=\"1\" width=\"100%\">"
}
{
	if ($0 ~ /^--*$/) {
		if (term == 1) {
			print "</td></tr>"
			term = 0
		}
		print "<tr>"
	} else if ($0 ~ /^r[0-9][0-9]* \| .*$/) {
		print "<td valign=\"top\" width=\"1%\">" substr($1, 2) "<br />"
		if ($3 == "vapier") {
			$3 = "SpankMan"
		} else if ($3 == "antarus") {
			$3 = "WarnerBro"
		}
		print $3 "</td><td>"
	} else if ($0 ~ /^..*$/) {
		print $0
		term = 1
	}
}
END {
	if (term == 1) {
		print "</td></tr>"
	}
	print "</table></html>"
}
' | elinks -dump | sed -e '/+-\++/d' -e 's/|[-+]\+|//'
