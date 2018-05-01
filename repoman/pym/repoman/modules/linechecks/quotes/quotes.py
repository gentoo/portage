
import re

from repoman.modules.linechecks.base import LineCheck


class EbuildQuote(LineCheck):
	"""Ensure ebuilds have valid quoting around things like D,FILESDIR, etc..."""

	repoman_check_name = 'ebuild.minorsyn'
	_message_commands = [
		"die", "echo", "eerror", "einfo", "elog", "eqawarn", "ewarn"]
	_message_re = re.compile(
		r'\s(' + "|".join(_message_commands) + r')\s+"[^"]*"\s*$')
	_ignored_commands = ["local", "export"] + _message_commands
	ignore_line = re.compile(
		r'(^$)|(^\s*#.*)|(^\s*\w+=.*)' +
		r'|(^\s*(' + "|".join(_ignored_commands) + r')\s+)')
	ignore_comment = False
	var_names = [
                "D", "DISTDIR", "FILESDIR", "S", "T", "ROOT", "BROOT", "WORKDIR"]

	# EAPI=3/Prefix vars
	var_names += ["ED", "EPREFIX", "EROOT"]

	# variables for games.eclass
	var_names += [
		"Ddir", "GAMES_PREFIX_OPT", "GAMES_DATADIR",
		"GAMES_DATADIR_BASE", "GAMES_SYSCONFDIR", "GAMES_STATEDIR",
		"GAMES_LOGDIR", "GAMES_BINDIR"]

	# variables for multibuild.eclass
	var_names += ["BUILD_DIR"]

	var_names = "(%s)" % "|".join(var_names)
	var_reference = re.compile(
		r'\$(\{%s\}|%s\W)' % (var_names, var_names))
	missing_quotes = re.compile(
		r'(\s|^)[^"\'\s]*\$\{?%s\}?[^"\'\s]*(\s|$)' % var_names)
	cond_begin = re.compile(r'(^|\s+)\[\[($|\\$|\s+)')
	cond_end = re.compile(r'(^|\s+)\]\]($|\\$|\s+)')

	def check(self, num, line):
		if self.var_reference.search(line) is None:
			return
		# There can be multiple matches / violations on a single line. We
		# have to make sure none of the matches are violators. Once we've
		# found one violator, any remaining matches on the same line can
		# be ignored.
		pos = 0
		while pos <= len(line) - 1:
			missing_quotes = self.missing_quotes.search(line, pos)
			if not missing_quotes:
				break
			# If the last character of the previous match is a whitespace
			# character, that character may be needed for the next
			# missing_quotes match, so search overlaps by 1 character.
			group = missing_quotes.group()
			pos = missing_quotes.end() - 1

			# Filter out some false positives that can
			# get through the missing_quotes regex.
			if self.var_reference.search(group) is None:
				continue

			# Filter matches that appear to be an
			# argument to a message command.
			# For example: false || ewarn "foo $WORKDIR/bar baz"
			message_match = self._message_re.search(line)
			if message_match is not None and \
				message_match.start() < pos and \
				message_match.end() > pos:
				break

			# This is an attempt to avoid false positives without getting
			# too complex, while possibly allowing some (hopefully
			# unlikely) violations to slip through. We just assume
			# everything is correct if the there is a ' [[ ' or a ' ]] '
			# anywhere in the whole line (possibly continued over one
			# line).
			if self.cond_begin.search(line) is not None:
				continue
			if self.cond_end.search(line) is not None:
				continue

			# Any remaining matches on the same line can be ignored.
			return self.errors['MISSING_QUOTES_ERROR']
