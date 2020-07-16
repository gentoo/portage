#!/usr/bin/python -b
# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os
import re
import sys

here_doc_re = re.compile(br'.*\s<<[-]?(\w+)$')
func_start_re = re.compile(br'^[-\w]+\s*\(\)\s*$')
func_end_re = re.compile(br'^\}$')

var_assign_re = re.compile(br'(^|^declare\s+-\S+\s+|^declare\s+|^export\s+)([^=\s]+)=("|\')?.*$')
close_quote_re = re.compile(br'(\\"|"|\')\s*$')
readonly_re = re.compile(br'^declare\s+-(\S*)r(\S*)\s+')
# declare without assignment
var_declare_re = re.compile(br'^declare(\s+-\S+)?\s+([^=\s]+)\s*$')

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
		declare_opts = b''
		for i in (1, 2):
			group = readonly_match.group(i)
			if group is not None:
				declare_opts += group
		if declare_opts:
			line = b'declare -' + declare_opts + \
				b' ' + line[readonly_match.end():]
		else:
			line = b'declare ' + line[readonly_match.end():]
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
				file_out.write(line.replace(b"\1", b""))
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
					file_out.write(line.replace(b"\1", b""))
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
			here_doc_delim = re.compile(b'^' + here_doc.group(1) + b'$')
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
	args = sys.argv[1:]

	if '-h' in args or '--help' in args:
		sys.stdout.write(usage + "\n")
		sys.stdout.flush()
		sys.exit(os.EX_OK)

	if len(args) != 1:
		sys.stderr.write(usage + "\n")
		sys.stderr.write("Exactly one PATTERN argument required.\n")
		sys.stderr.flush()
		sys.exit(2)

	file_in = sys.stdin.buffer
	file_out = sys.stdout.buffer
	var_pattern = os.fsencode(args[0]).split()

	# Filter invalid variable names that are not supported by bash.
	var_pattern.append(br'\d.*')
	var_pattern.append(br'.*\W.*')

	var_pattern = b'^(' + b'|'.join(var_pattern) + b')$'
	filter_bash_environment(
		re.compile(var_pattern), file_in, file_out)
	file_out.flush()
