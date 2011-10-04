#!/usr/bin/python
# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import codecs
import io
import optparse
import os
import re
import sys

here_doc_re = re.compile(r'.*\s<<[-]?(\w+)$')
func_start_re = re.compile(r'^[-\w]+\s*\(\)\s*$')
func_end_re = re.compile(r'^\}$')

var_assign_re = re.compile(r'(^|^declare\s+-\S+\s+|^declare\s+|^export\s+)([^=\s]+)=("|\')?.*$')
close_quote_re = re.compile(r'(\\"|"|\')\s*$')
readonly_re = re.compile(r'^declare\s+-(\S*)r(\S*)\s+')
# declare without assignment
var_declare_re = re.compile(r'^declare(\s+-\S+)?\s+([^=\s]+)\s*$')

def have_end_quote(quote, line):
	"""
	Check if the line has an end quote (useful for handling multi-line
	quotes). This handles escaped double quotes that may occur at the
	end of a line. The posix spec does not allow escaping of single
	quotes inside of single quotes, so that case is not handled.
	"""
	close_quote_match = close_quote_re.search(line)
	return close_quote_match is not None and \
		close_quote_match.group(1) == quote

def filter_declare_readonly_opt(line):
	readonly_match = readonly_re.match(line)
	if readonly_match is not None:
		declare_opts = ''
		for i in (1, 2):
			group = readonly_match.group(i)
			if group is not None:
				declare_opts += group
		if declare_opts:
			line = 'declare -%s %s' % \
				(declare_opts, line[readonly_match.end():])
		else:
			line = 'declare ' + line[readonly_match.end():]
	return line

def filter_bash_environment(pattern, file_in, file_out):
	# Filter out any instances of the \1 character from variable values
	# since this character multiplies each time that the environment
	# is saved (strange bash behavior). This can eventually result in
	# mysterious 'Argument list too long' errors from programs that have
	# huge strings of \1 characters in their environment. See bug #222091.
	here_doc_delim = None
	in_func = None
	multi_line_quote = None
	multi_line_quote_filter = None
	for line in file_in:
		if multi_line_quote is not None:
			if not multi_line_quote_filter:
				file_out.write(line.replace("\1", ""))
			if have_end_quote(multi_line_quote, line):
				multi_line_quote = None
				multi_line_quote_filter = None
			continue
		if here_doc_delim is None and in_func is None:
			var_assign_match = var_assign_re.match(line)
			if var_assign_match is not None:
				quote = var_assign_match.group(3)
				filter_this = pattern.match(var_assign_match.group(2)) \
					is not None
				# Exclude the start quote when searching for the end quote,
				# to ensure that the start quote is not misidentified as the
				# end quote (happens if there is a newline immediately after
				# the start quote).
				if quote is not None and not \
					have_end_quote(quote, line[var_assign_match.end(2)+2:]):
					multi_line_quote = quote
					multi_line_quote_filter = filter_this
				if not filter_this:
					line = filter_declare_readonly_opt(line)
					file_out.write(line.replace("\1", ""))
				continue
			else:
				declare_match = var_declare_re.match(line)
				if declare_match is not None:
					# declare without assignment
					filter_this = pattern.match(declare_match.group(2)) \
						is not None
					if not filter_this:
						line = filter_declare_readonly_opt(line)
						file_out.write(line)
					continue

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
		# Note: here-documents are handled before functions since otherwise
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
		# This line is not recognized as part of a variable assignment,
		# function definition, or here document, so just allow it to
		# pass through.
		file_out.write(line)

if __name__ == "__main__":
	description = "Filter out variable assignments for variable " + \
		"names matching a given PATTERN " + \
		"while leaving bash function definitions and here-documents " + \
		"intact. The PATTERN is a space separated list of variable names" + \
		" and it supports python regular expression syntax."
	usage = "usage: %s PATTERN" % os.path.basename(sys.argv[0])
	parser = optparse.OptionParser(description=description, usage=usage)
	options, args = parser.parse_args(sys.argv[1:])
	if len(args) != 1:
		parser.error("Missing required PATTERN argument.")
	file_in = sys.stdin
	file_out = sys.stdout
	if sys.hexversion >= 0x3000000:
		file_in = codecs.iterdecode(sys.stdin.buffer.raw,
			'utf_8', errors='replace')
		file_out = io.TextIOWrapper(sys.stdout.buffer,
			'utf_8', errors='backslashreplace')

	var_pattern = args[0].split()

	# Filter invalid variable names that are not supported by bash.
	var_pattern.append(r'\d.*')
	var_pattern.append(r'.*\W.*')

	var_pattern = "^(%s)$" % "|".join(var_pattern)
	filter_bash_environment(
		re.compile(var_pattern), file_in, file_out)
	file_out.flush()
