#!/usr/bin/env bash

# bla bla
# probably can be done much better, but I got tired of copy 'n' paste
# from mutt into a commit message ...

[[ -z $1 ]] && exit -1

svn log ../../trunk -r$1 | awk -v revs=$1 '
BEGIN {
	term = 0
	print "<html>"
	print "Merged from trunk " revs
	print "<table border=\"1\">"
}
{
	if ($0 ~ /^--*$/) {
		if (term == 1) {
			print "</td></tr>"
		}
		print "<tr>"
	} else if ($0 ~ /^r[0-9][0-9]* \| .*$/) {
		print "<td valign=\"top\">" substr($1, 2) "<br />"
		if ($3 == "vapier") {
			$3 = "SpankMan"
		} else if ($3 == "antarus") {
			$3 = "WarnerBro"
		}
		print $3 "</td><td>"
	} else if ($0 ~ /^..*$/) {
		if (noprint == 0) {
			print $0
			term = 1
		}
	}
}
END {
	if (term == 1) {
		print "</td></tr>"
	}
	print "</table></html>"
}
' | elinks -dump
