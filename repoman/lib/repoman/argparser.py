# repoman: Argument parser
# Copyright 2007-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""This module contains functions used in Repoman to parse CLI arguments."""

import argparse
import logging
import sys

# import our initialized portage instance
from repoman._portage import portage

from portage import _unicode_decode
from portage import util


def parse_args(argv, repoman_default_opts):
	"""Use a customized optionParser to parse command line arguments for repoman
	Args:
		argv - a sequence of command line arguments
	Returns:
		(opts, args), just like a call to parser.parse_args()
	"""

	argv = portage._decode_argv(argv)

	modes = {
		'commit': 'Run a scan then commit changes',
		'ci': 'Run a scan then commit changes',
		'fix': 'Fix simple QA issues (stray digests, missing digests)',
		'full': 'Scan directory tree and print all issues (not a summary)',
		'help': 'Show this screen',
		'manifest': 'Generate a Manifest (fetches files if necessary)',
		'manifest-check': 'Check Manifests for missing or incorrect digests',
		'scan': 'Scan directory tree for QA issues'
	}

	output_choices = {
		'default': 'The normal output format',
		'column': 'Columnar output suitable for use with grep'
	}

	mode_keys = list(modes)
	mode_keys.sort()

	output_keys = sorted(output_choices)

	parser = argparse.ArgumentParser(
		usage="repoman [options] [mode]",
		description="Modes: %s" % " | ".join(mode_keys),
		epilog="For more help consult the man page.")

	parser.add_argument(
		'-a', '--ask', dest='ask', action='store_true',
		default=False,
		help='Request a confirmation before commiting')

	parser.add_argument(
		'-b', '--bug', dest='bug', action='append', metavar='<BUG-NO|BUG-URL>',
		default=[],
		help=(
			'Mention a Gentoo or upstream bug in the commit footer; '
			'takes either Gentoo bug number or full bug URL'))

	parser.add_argument(
		'-c', '--closes', dest='closes', action='append', metavar='<PR-NO|PR-URL>',
		default=[],
		help=(
			'Adds a Closes footer to close GitHub pull request (or compatible); '
			'takes either GitHub PR number or full PR URL'))

	parser.add_argument(
		'-m', '--commitmsg', dest='commitmsg',
		help='specify a commit message on the command line')

	parser.add_argument(
		'-M', '--commitmsgfile', dest='commitmsgfile',
		help='specify a path to a file that contains a commit message')

	parser.add_argument(
		'--digest', choices=('y', 'n'), metavar='<y|n>',
		help='Automatically update Manifest digests for modified files')

	parser.add_argument(
		'-p', '--pretend', dest='pretend', default=False,
		action='store_true',
		help='don\'t commit or fix anything; just show what would be done')

	parser.add_argument(
		'-q', '--quiet', dest="quiet", action="count",
		default=0,
		help='do not print unnecessary messages')

	parser.add_argument(
		'--echangelog', choices=('y', 'n', 'force'), metavar="<y|n|force>",
		help=(
			'for commit mode, call echangelog if ChangeLog is unmodified (or '
			'regardless of modification if \'force\' is specified)'))

	parser.add_argument(
		'--experimental-inherit', choices=('y', 'n'), metavar="<y|n>",
		default='n',
		help=(
			'Enable experimental inherit.missing checks which may misbehave'
			' when the internal eclass database becomes outdated'))

	parser.add_argument(
		'--experimental-repository-modules', choices=('y', 'n'), metavar="<y|n>",
		default='n',
		help='Enable experimental repository modules')

	parser.add_argument(
		'-f', '--force', dest='force', action='store_true',
		default=False,
		help='Commit with QA violations')

	parser.add_argument(
		'-S', '--straight-to-stable', dest='straight_to_stable',
		default=False, action='store_true',
		help='Allow committing straight to stable')

	parser.add_argument(
		'--vcs', dest='vcs',
		help='Force using specific VCS instead of autodetection')

	parser.add_argument(
		'-v', '--verbose', dest="verbosity", action='count',
		help='be very verbose in output', default=0)

	parser.add_argument(
		'-V', '--version', dest='version', action='store_true',
		help='show version info')

	parser.add_argument(
		'-x', '--xmlparse', dest='xml_parse', action='store_true',
		default=False,
		help='forces the metadata.xml parse check to be carried out')

	parser.add_argument(
		'--if-modified', choices=('y', 'n'), default='n',
		metavar="<y|n>",
		help='only check packages that have uncommitted modifications')

	parser.add_argument(
		'-i', '--ignore-arches', dest='ignore_arches', action='store_true',
		default=False,
		help='ignore arch-specific failures (where arch != host)')

	parser.add_argument(
		"--ignore-default-opts",
		action="store_true",
		help="do not use the REPOMAN_DEFAULT_OPTS environment variable")

	parser.add_argument(
		'-I', '--ignore-masked', dest='ignore_masked', action='store_true',
		default=False,
		help='ignore masked packages (not allowed with commit mode)')

	parser.add_argument(
		'--include-arches',
		dest='include_arches', metavar='ARCHES', action='append',
		help=(
			'A space separated list of arches used to '
			'filter the selection of profiles for dependency checks'))

	parser.add_argument(
		'--include-profiles',
		dest='include_profiles', metavar='PROFILES', action='append',
		help=(
			'A space separated list of profiles used to '
			'define the selection of profiles for dependency checks'))

	parser.add_argument(
		'-d', '--include-dev', dest='include_dev', action='store_true',
		default=False,
		help='include dev profiles in dependency checks')

	parser.add_argument(
		'-e', '--include-exp-profiles', choices=('y', 'n'), metavar='<y|n>',
		default=False,
		help='include exp profiles in dependency checks')

	parser.add_argument(
		'--unmatched-removal', dest='unmatched_removal', action='store_true',
		default=False,
		help=(
			'enable strict checking of package.mask and package.unmask files'
			' for unmatched removal atoms'))

	parser.add_argument(
		'--without-mask', dest='without_mask', action='store_true',
		default=False,
		help=(
			'behave as if no package.mask entries exist'
			' (not allowed with commit mode)'))

	parser.add_argument(
		'--output-style', dest='output_style', choices=output_keys,
		help='select output type', default='default')

	parser.add_argument(
		'-j', '--jobs', dest='jobs', action='store', type=int, default=1,
		help='Specifies the number of jobs (processes) to run simultaneously.')

	parser.add_argument(
		'-l', '--load-average', dest='load_average', action='store', type=float, default=None,
		help='Specifies that no new jobs (processes) should be started if there are others '
			'jobs running and the load average is at least load (a floating-point number).')

	parser.add_argument(
		'--mode', dest='mode', choices=mode_keys,
		help='specify which mode repoman will run in (default=full)')

	# Modes help is included earlier, in the parser description.
	parser.add_argument(
		'mode_positional', nargs='?', metavar='mode', choices=mode_keys,
		help=argparse.SUPPRESS)

	opts = parser.parse_args(argv[1:])

	if not opts.ignore_default_opts:
		default_opts = util.shlex_split(repoman_default_opts)
		if default_opts:
			opts = parser.parse_args(default_opts + sys.argv[1:])

	args = []
	if opts.mode is not None:
		args.append(opts.mode)
	if opts.mode_positional is not None:
		args.append(opts.mode_positional)

	if len(set(args)) > 1:
		parser.error("multiple modes specified: %s" % " ".join(args))

	opts.mode = args[0] if args else None

	if opts.mode == 'help':
		parser.print_help()
		parser.exit()

	if not opts.mode:
		opts.mode = 'full'

	if opts.mode == 'ci':
		opts.mode = 'commit'  # backwards compat shortcut

	# Use verbosity and quiet options to appropriately fiddle with the loglevel
	for val in range(opts.verbosity):
		logger = logging.getLogger()
		logger.setLevel(logger.getEffectiveLevel() - 10)

	for val in range(opts.quiet):
		logger = logging.getLogger()
		logger.setLevel(logger.getEffectiveLevel() + 10)

	if opts.mode == 'commit' and opts.commitmsg:
		opts.commitmsg = _unicode_decode(opts.commitmsg)

	if opts.mode == 'commit' and not (opts.force or opts.pretend):
		if opts.ignore_masked:
			opts.ignore_masked = False
			logging.warn('Commit mode automatically disables --ignore-masked')
		if opts.without_mask:
			opts.without_mask = False
			logging.warn('Commit mode automatically disables --without-mask')

	return (opts, args)
