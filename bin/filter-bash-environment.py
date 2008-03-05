#!/usr/bin/env python
# Copyright 1999-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os, re, sys

egrep_compat_map = {
	"[:alnum:]" : r'\w',
	"[:digit:]" : r'\d',
	"[:space:]" : r'\s',
}

here_doc_re = re.compile(r'.*\s<<[-]?(\w+)$')
func_start_re = re.compile(r'^[-\w]+\s*\(\)\s*$')
func_end_re = re.compile(r'^\}$')

var_assign_re = re.compile(r'(^|^declare\s+-\S+\s+|^export\s+)([^=\s]+)=.*$')

def compile_egrep_pattern(s):
	for k, v in egrep_compat_map.iteritems():
		s = s.replace(k, v)
	return re.compile(s)

def filter_bash_environment(pattern, file_in, file_out):
	here_doc_delim = None
	in_func = None
	for line in file_in:
		if here_doc_delim is not None:
			if here_doc_delim.match(line):
				here_doc_delim = None
			file_out.write(line)
			continue
		here_doc = here_doc_re.match(line)
		if here_doc is not None:
			here_doc_delim = re.compile("^%s$" % here_doc.group(1))
			file_out.write(line)
			continue
		# Note: here-documents are handled before fuctions since otherwise
		# it would be possible for the content of a here-document to be
		# mistaken as the end of a function.
		if in_func:
			if func_end_re.match(line) is not None:
				in_func = None
			file_out.write(line)
			continue
		in_func = func_start_re.match(line)
		if in_func is not None:
			file_out.write(line)
			continue
		var_assign_match = var_assign_re.match(line)
		if var_assign_match is not None:
			if pattern.match(var_assign_match.group(2)) is None:
				file_out.write(line)
			continue
		# TODO: properly handle multi-line variable assignments
		# like those which the 'export' builtin can produce.
		file_out.write(line)

if __name__ == "__main__":
	description = "Filter out variable assignments for varable " + \
		"names matching a given PATTERN " + \
		"while leaving bash function definitions and here-documents " + \
		"intact. The PATTERN should use python regular expression syntax" + \
		" but [:digit:], [:space:] and " + \
		"[:alnum:] character classes will be automatically translated " + \
		"for compatibility with egrep syntax."
	usage = "usage: %s PATTERN" % os.path.basename(sys.argv[0])
	from optparse import OptionParser
	parser = OptionParser(description=description, usage=usage)
	options, args = parser.parse_args(sys.argv[1:])
	if len(args) != 1:
		parser.error("Missing required PATTERN argument.")
	file_in = sys.stdin
	file_out = sys.stdout
	filter_bash_environment(
		compile_egrep_pattern(args[0]), file_in, file_out)
	file_out.flush()
