# Copyright 1998-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

__docformat__ = "epytext"

import codecs
import commands
import errno
import formatter
import os
import re
import shlex
import sys

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util:writemsg',
)

from portage.const import COLOR_MAP_FILE
from portage.exception import CommandNotFound, FileNotFound, \
	ParseError, PermissionDenied, PortageException

havecolor=1
dotitles=1

codes = {}
"""Maps color class to tuple of attribute names."""

color_codes = {}
"""Maps attribute name to ansi code."""

esc_seq = "\x1b["

color_codes["normal"]       =  esc_seq + "0m"
color_codes["reset"]        =  esc_seq + "39;49;00m"

color_codes["bold"]         =  esc_seq + "01m"
color_codes["faint"]        =  esc_seq + "02m"
color_codes["standout"]     =  esc_seq + "03m"
color_codes["underline"]    =  esc_seq + "04m"
color_codes["blink"]        =  esc_seq + "05m"
color_codes["overline"]     =  esc_seq + "06m"
color_codes["reverse"]      =  esc_seq + "07m"
color_codes["invisible"]    =  esc_seq + "08m"

color_codes["no-attr"]      = esc_seq + "22m"
color_codes["no-standout"]  = esc_seq + "23m"
color_codes["no-underline"] = esc_seq + "24m"
color_codes["no-blink"]     = esc_seq + "25m"
color_codes["no-overline"]  = esc_seq + "26m"
color_codes["no-reverse"]   = esc_seq + "27m"

color_codes["bg_black"]      = esc_seq + "40m"
color_codes["bg_darkred"]    = esc_seq + "41m"
color_codes["bg_darkgreen"]  = esc_seq + "42m"
color_codes["bg_brown"]      = esc_seq + "43m"
color_codes["bg_darkblue"]   = esc_seq + "44m"
color_codes["bg_purple"]     = esc_seq + "45m"
color_codes["bg_teal"]       = esc_seq + "46m"
color_codes["bg_lightgray"]  = esc_seq + "47m"
color_codes["bg_default"]    = esc_seq + "49m"
color_codes["bg_darkyellow"] = color_codes["bg_brown"]

def color(fg, bg="default", attr=["normal"]):
	mystr = color_codes[fg]
	for x in [bg]+attr:
		mystr += color_codes[x]
	return mystr


ansi_color_codes = []
for x in xrange(30, 38):
	ansi_color_codes.append("%im" % x)
	ansi_color_codes.append("%i;01m" % x)

rgb_ansi_colors = ['0x000000', '0x555555', '0xAA0000', '0xFF5555', '0x00AA00',
	'0x55FF55', '0xAA5500', '0xFFFF55', '0x0000AA', '0x5555FF', '0xAA00AA',
	'0xFF55FF', '0x00AAAA', '0x55FFFF', '0xAAAAAA', '0xFFFFFF']

for x in xrange(len(rgb_ansi_colors)):
	color_codes[rgb_ansi_colors[x]] = esc_seq + ansi_color_codes[x]

del x

color_codes["black"]     = color_codes["0x000000"]
color_codes["darkgray"]  = color_codes["0x555555"]

color_codes["red"]       = color_codes["0xFF5555"]
color_codes["darkred"]   = color_codes["0xAA0000"]

color_codes["green"]     = color_codes["0x55FF55"]
color_codes["darkgreen"] = color_codes["0x00AA00"]

color_codes["yellow"]    = color_codes["0xFFFF55"]
color_codes["brown"]     = color_codes["0xAA5500"]

color_codes["blue"]      = color_codes["0x5555FF"]
color_codes["darkblue"]  = color_codes["0x0000AA"]

color_codes["fuchsia"]   = color_codes["0xFF55FF"]
color_codes["purple"]    = color_codes["0xAA00AA"]

color_codes["turquoise"] = color_codes["0x55FFFF"]
color_codes["teal"]      = color_codes["0x00AAAA"]

color_codes["white"]     = color_codes["0xFFFFFF"]
color_codes["lightgray"] = color_codes["0xAAAAAA"]

color_codes["darkteal"]   = color_codes["turquoise"]
# Some terminals have darkyellow instead of brown.
color_codes["0xAAAA00"]   = color_codes["brown"]
color_codes["darkyellow"] = color_codes["0xAAAA00"]



# Colors from /etc/init.d/functions.sh
codes["NORMAL"]     = ( "normal", )
codes["GOOD"]       = ( "green", )
codes["WARN"]       = ( "yellow", )
codes["BAD"]        = ( "red", )
codes["HILITE"]     = ( "teal", )
codes["BRACKET"]    = ( "blue", )

# Portage functions
codes["INFORM"]                  = ( "darkgreen", )
codes["UNMERGE_WARN"]            = ( "red", )
codes["SECURITY_WARN"]           = ( "red", )
codes["MERGE_LIST_PROGRESS"]     = ( "yellow", )
codes["PKG_BLOCKER"]             = ( "red", )
codes["PKG_BLOCKER_SATISFIED"]   = ( "darkblue", )
codes["PKG_MERGE"]               = ( "darkgreen", )
codes["PKG_MERGE_SYSTEM"]        = ( "darkgreen", )
codes["PKG_MERGE_WORLD"]         = ( "green", )
codes["PKG_UNINSTALL"]           = ( "red", )
codes["PKG_NOMERGE"]             = ( "darkblue", )
codes["PKG_NOMERGE_SYSTEM"]      = ( "darkblue", )
codes["PKG_NOMERGE_WORLD"]       = ( "blue", )
codes["PROMPT_CHOICE_DEFAULT"]   = ( "green", )
codes["PROMPT_CHOICE_OTHER"]     = ( "red", )

def _parse_color_map(onerror=None):
	"""
	Parse /etc/portage/color.map and return a dict of error codes.

	@param onerror: an optional callback to handle any ParseError that would
		otherwise be raised
	@type onerror: callable
	@rtype: dict
	@return: a dictionary mapping color classes to color codes
	"""
	myfile = COLOR_MAP_FILE
	ansi_code_pattern = re.compile("^[0-9;]*m$") 
	quotes = '\'"'
	def strip_quotes(token):
		if token[0] in quotes and token[0] == token[-1]:
			token = token[1:-1]
		return token
	try:
		lineno=0
		for line in codecs.open( myfile, mode = 'r', errors = 'replace' ):
			lineno += 1

			commenter_pos = line.find("#")
			line = line[:commenter_pos].strip()
			
			if len(line) == 0:
				continue
			
			split_line = line.split("=")
			if len(split_line) != 2:
				e = ParseError("'%s', line %s: %s" % (
					myfile, lineno,
					"expected exactly one occurence of '=' operator"))
				raise e
				if onerror:
					onerror(e)
				else:
					raise e
				continue

			k = strip_quotes(split_line[0].strip())
			v = strip_quotes(split_line[1].strip())
			if not k in codes and not k in color_codes:
				e = ParseError("'%s', line %s: %s'%s'" % (
					myfile, lineno,
					"Unknown variable: ", k))
				if onerror:
					onerror(e)
				else:
					raise e
				continue
			if ansi_code_pattern.match(v):
				if k in codes:
					codes[k] = ( esc_seq + v, )
				elif k in color_codes:
					color_codes[k] = esc_seq + v
			else:
				code_list = []
				for x in v.split():
					if x in color_codes:
						if k in codes:
							code_list.append(x)
						elif k in color_codes:
							code_list.append(color_codes[x])
					else:
						e = ParseError("'%s', line %s: %s'%s'" % (
							myfile, lineno,
							"Undefined: ", x))
						if onerror:
							onerror(e)
						else:
							raise e
				if k in codes:
					codes[k] = tuple(code_list)
				elif k in color_codes:
					color_codes[k] = "".join(code_list)
	except (IOError, OSError), e:
		if e.errno == errno.ENOENT:
			raise FileNotFound(myfile)
		elif e.errno == errno.EACCES:
			raise PermissionDenied(myfile)
		raise

def nc_len(mystr):
	tmp = re.sub(esc_seq + "^m]+m", "", mystr);
	return len(tmp)

_legal_terms_re = re.compile(r'^(xterm|xterm-color|Eterm|aterm|rxvt|screen|kterm|rxvt-unicode|gnome|interix)')
_disable_xtermTitle = None
_max_xtermTitle_len = 253

def xtermTitle(mystr, raw=False):
	global _disable_xtermTitle
	if _disable_xtermTitle is None:
		_disable_xtermTitle = not (sys.stderr.isatty() and \
		'TERM' in os.environ and \
		_legal_terms_re.match(os.environ['TERM']) is not None)

	if dotitles and not _disable_xtermTitle:
		# If the title string is too big then the terminal can
		# misbehave. Therefore, truncate it if it's too big.
		if len(mystr) > _max_xtermTitle_len:
			mystr = mystr[:_max_xtermTitle_len]
		if not raw:
			mystr = '\x1b]0;%s\x07' % mystr
		sys.stderr.write(mystr)
		sys.stderr.flush()

default_xterm_title = None

def xtermTitleReset():
	global default_xterm_title
	if default_xterm_title is None:
		prompt_command = os.getenv('PROMPT_COMMAND')
		if prompt_command == "":
			default_xterm_title = ""
		elif prompt_command is not None:
			if dotitles and "TERM" in os.environ and sys.stderr.isatty():
				from portage.process import find_binary, spawn
				shell = os.environ.get("SHELL")
				if not shell or not os.access(shell, os.EX_OK):
					shell = find_binary("sh")
				if shell:
					spawn([shell, "-c", prompt_command], env=os.environ,
						fd_pipes={0:sys.stdin.fileno(),1:sys.stderr.fileno(),
						2:sys.stderr.fileno()})
				else:
					os.system(prompt_command)
			return
		else:
			pwd = os.getenv('PWD','')
			home = os.getenv('HOME', '')
			if home != '' and pwd.startswith(home):
				pwd = '~' + pwd[len(home):]
			default_xterm_title = '\x1b]0;%s@%s:%s\x07' % (
				os.getenv('LOGNAME', ''), os.getenv('HOSTNAME', '').split('.', 1)[0], pwd)
	xtermTitle(default_xterm_title, raw=True)

def notitles():
	"turn off title setting"
	dotitles=0

def nocolor():
	"turn off colorization"
	global havecolor
	havecolor=0

def resetColor():
	return color_codes["reset"]

def map_code_to_color_code(code):
	ret = ""
	for color_code in codes[code]:
		# allow stuff that has found it's way through ansi_code_pattern
		ret += color_codes.get(color_code, color_code)
	return ret

def colorize(color_key, text):
	global havecolor
	if havecolor:
		if color_key in color_codes:
			return color_codes[color_key] + text + color_codes["reset"]
		elif color_key in codes:
			return map_code_to_color_code(color_key) + text + color_codes["reset"]
		else:
			return text
	else:
		return text

compat_functions_colors = ["bold","white","teal","turquoise","darkteal",
	"fuchsia","purple","blue","darkblue","green","darkgreen","yellow",
	"brown","darkyellow","red","darkred"]

def create_color_func(color_key):
	def derived_func(*args):
		newargs = list(args)
		newargs.insert(0, color_key)
		return colorize(*newargs)
	return derived_func

for c in compat_functions_colors:
	globals()[c] = create_color_func(c)

class ConsoleStyleFile(object):
	"""
	A file-like object that behaves something like
	the colorize() function. Style identifiers
	passed in via the new_styles() method will be used to
	apply console codes to output.
	"""
	def __init__(self, f):
		self._file = f
		self._styles = None
		self.write_listener = None

	def new_styles(self, styles):
		self._styles = styles

	def write(self, s):
		global havecolor
		if havecolor and self._styles:
			for style in self._styles:
				self._file.write(map_code_to_color_code(style))
			self._file.write(s)
			self._file.write(color_codes["reset"])
		else:
			self._file.write(s)
		if self.write_listener:
			self.write_listener.write(s)

	def writelines(self, lines):
		for s in lines:
			self.write(s)

	def flush(self):
		self._file.flush()

	def close(self):
		self._file.close()

class StyleWriter(formatter.DumbWriter):
	"""
	This is just a DumbWriter with a hook in the new_styles() method
	that passes a styles tuple as a single argument to a callable
	style_listener attribute.
	"""
	def __init__(self, **kwargs):
		formatter.DumbWriter.__init__(self, **kwargs)
		self.style_listener = None

	def new_styles(self, styles):
		formatter.DumbWriter.new_styles(self, styles)
		if self.style_listener:
			self.style_listener(styles)

def get_term_size():
	"""
	Get the number of lines and columns of the tty that is connected to
	stdout.  Returns a tuple of (lines, columns) or (-1, -1) if an error
	occurs. The curses module is used if available, otherwise the output of
	`stty size` is parsed.
	"""
	if not sys.stdout.isatty():
		return -1, -1
	try:
		import curses
		try:
			curses.setupterm()
			return curses.tigetnum('lines'), curses.tigetnum('cols')
		except curses.error:
			pass
	except ImportError:
		pass
	st, out = commands.getstatusoutput('stty size')
	if st == os.EX_OK:
		out = out.split()
		if len(out) == 2:
			try:
				return int(out[0]), int(out[1])
			except ValueError:
				pass
	return -1, -1

def set_term_size(lines, columns, fd):
	"""
	Set the number of lines and columns for the tty that is connected to fd.
	For portability, this simply calls `stty rows $lines columns $columns`.
	"""
	from portage.process import spawn
	cmd = ["stty", "rows", str(lines), "columns", str(columns)]
	try:
		spawn(cmd, env=os.environ, fd_pipes={0:fd})
	except CommandNotFound:
		writemsg("portage: stty: command not found\n", noiselevel=-1)

class EOutput(object):
	"""
	Performs fancy terminal formatting for status and informational messages.

	The provided methods produce identical terminal output to the eponymous
	functions in the shell script C{/sbin/functions.sh} and also accept
	identical parameters.

	This is not currently a drop-in replacement however, as the output-related
	functions in C{/sbin/functions.sh} are oriented for use mainly by system
	init scripts and ebuilds and their output can be customized via certain
	C{RC_*} environment variables (see C{/etc/conf.d/rc}). B{EOutput} is not
	customizable in this manner since it's intended for more general uses.
	Likewise, no logging is provided.

	@ivar quiet: Specifies if output should be silenced.
	@type quiet: BooleanType
	@ivar term_columns: Width of terminal in characters. Defaults to the value
		specified by the shell's C{COLUMNS} variable, else to the queried tty
		size, else to C{80}.
	@type term_columns: IntType
	"""

	def __init__(self, quiet=False):
		self.__last_e_cmd = ""
		self.__last_e_len = 0
		self.quiet = quiet
		lines, columns = get_term_size()
		if columns <= 0:
			columns = 80
		# Adjust columns so that eend works properly on a standard BSD console.
		if os.environ.get("TERM") in ("cons25", "dumb"):
			columns = columns - 1
		self.term_columns = columns
		sys.stdout.flush()
		sys.stderr.flush()

	def __eend(self, caller, errno, msg):
		if errno == 0:
			status_brackets = colorize("BRACKET", "[ ") + colorize("GOOD", "ok") + colorize("BRACKET", " ]")
		else:
			status_brackets = colorize("BRACKET", "[ ") + colorize("BAD", "!!") + colorize("BRACKET", " ]")
			if msg:
				if caller == "eend":
					self.eerror(msg[0])
				elif caller == "ewend":
					self.ewarn(msg[0])
		if self.__last_e_cmd != "ebegin":
			self.__last_e_len = 0
		if not self.quiet:
			out = sys.stdout
			out.write("%*s%s\n" % ((self.term_columns - self.__last_e_len - 6),
				"", status_brackets))
			out.flush()

	def ebegin(self, msg):
		"""
		Shows a message indicating the start of a process.

		@param msg: A very brief (shorter than one line) description of the
			starting process.
		@type msg: StringType
		"""
		msg += " ..."
		if not self.quiet:
			self.einfon(msg)
		self.__last_e_len = len(msg) + 4
		self.__last_e_cmd = "ebegin"

	def eend(self, errno, *msg):
		"""
		Indicates the completion of a process, optionally displaying a message
		via L{eerror} if the process's exit status isn't C{0}.

		@param errno: A standard UNIX C{errno} code returned by processes upon
			exit.
		@type errno: IntType
		@param msg: I{(optional)} An error message, typically a standard UNIX
			error string corresponding to C{errno}.
		@type msg: StringType
		"""
		if not self.quiet:
			self.__eend("eend", errno, msg)
		self.__last_e_cmd = "eend"

	def eerror(self, msg):
		"""
		Shows an error message.

		@param msg: A very brief (shorter than one line) error message.
		@type msg: StringType
		"""
		out = sys.stderr
		if not self.quiet:
			if self.__last_e_cmd == "ebegin":
				out.write("\n")
			out.write(colorize("BAD", " * ") + msg + "\n")
			out.flush()
		self.__last_e_cmd = "eerror"

	def einfo(self, msg):
		"""
		Shows an informative message terminated with a newline.

		@param msg: A very brief (shorter than one line) informative message.
		@type msg: StringType
		"""
		out = sys.stdout
		if not self.quiet:
			if self.__last_e_cmd == "ebegin":
				out.write("\n")
			out.write(colorize("GOOD", " * ") + msg + "\n")
			out.flush()
		self.__last_e_cmd = "einfo"

	def einfon(self, msg):
		"""
		Shows an informative message terminated without a newline.

		@param msg: A very brief (shorter than one line) informative message.
		@type msg: StringType
		"""
		out = sys.stdout
		if not self.quiet:
			if self.__last_e_cmd == "ebegin":
				out.write("\n")
			out.write(colorize("GOOD", " * ") + msg)
			out.flush()
		self.__last_e_cmd = "einfon"

	def ewarn(self, msg):
		"""
		Shows a warning message.

		@param msg: A very brief (shorter than one line) warning message.
		@type msg: StringType
		"""
		out = sys.stderr
		if not self.quiet:
			if self.__last_e_cmd == "ebegin":
				out.write("\n")
			out.write(colorize("WARN", " * ") + msg + "\n")
			out.flush()
		self.__last_e_cmd = "ewarn"

	def ewend(self, errno, *msg):
		"""
		Indicates the completion of a process, optionally displaying a message
		via L{ewarn} if the process's exit status isn't C{0}.

		@param errno: A standard UNIX C{errno} code returned by processes upon
			exit.
		@type errno: IntType
		@param msg: I{(optional)} A warning message, typically a standard UNIX
			error string corresponding to C{errno}.
		@type msg: StringType
		"""
		if not self.quiet:
			self.__eend("ewend", errno, msg)
		self.__last_e_cmd = "ewend"

class ProgressBar(object):
	"""The interface is copied from the ProgressBar class from the EasyDialogs
	module (which is Mac only)."""
	def __init__(self, title=None, maxval=0, label=None):
		self._title = title
		self._maxval = maxval
		self._label = maxval
		self._curval = 0

	@property
	def curval(self):
		"""
		The current value (of type integer or long integer) of the progress
		bar. The normal access methods coerce curval between 0 and maxval. This
		attribute should not be altered directly.
		"""
		return self._curval

	@property
	def maxval(self):
		"""
		The maximum value (of type integer or long integer) of the progress
		bar; the progress bar (thermometer style) is full when curval equals
		maxval. If maxval is 0, the bar will be indeterminate (barber-pole).
		This attribute should not be altered directly.
		"""
		return self._maxval

	def title(self, newstr):
		"""Sets the text in the title bar of the progress dialog to newstr."""
		self._title = newstr

	def label(self, newstr):
		"""Sets the text in the progress box of the progress dialog to newstr."""
		self._label = newstr

	def set(self, value, maxval=None):
		"""
		Sets the progress bar's curval to value, and also maxval to max if the
		latter is provided. value is first coerced between 0 and maxval. The
		thermometer bar is updated to reflect the changes, including a change
		from indeterminate to determinate or vice versa.
		"""
		if maxval is not None:
			self._maxval = maxval
		if value < 0:
			value = 0
		elif value > self._maxval:
			value = self._maxval
		self._curval = value

	def inc(self, n=1):
		"""Increments the progress bar's curval by n, or by 1 if n is not
		provided. (Note that n may be negative, in which case the effect is a
		decrement.) The progress bar is updated to reflect the change. If the
		bar is indeterminate, this causes one ``spin'' of the barber pole. The
		resulting curval is coerced between 0 and maxval if incrementing causes
		it to fall outside this range.
		"""
		self.set(self._curval+n)

class TermProgressBar(ProgressBar):
	"""A tty progress bar similar to wget's."""
	def __init__(self, **kwargs):
		ProgressBar.__init__(self, **kwargs)
		lines, self.term_columns = get_term_size()
		self.file = sys.stdout
		self._min_columns = 11
		self._max_columns = 80
		# for indeterminate mode, ranges from 0.0 to 1.0
		self._position = 0.0

	def set(self, value, maxval=None):
		ProgressBar.set(self, value, maxval=maxval)
		self._display_image(self._create_image())

	def _display_image(self, image):
		self.file.write('\r')
		self.file.write(image)
		self.file.flush()

	def _create_image(self):
		cols = self.term_columns
		if cols > self._max_columns:
			cols = self._max_columns
		min_columns = self._min_columns
		curval = self._curval
		maxval = self._maxval
		position = self._position
		percentage_str_width = 4
		square_brackets_width = 2
		if cols < percentage_str_width:
			return ""
		bar_space = cols - percentage_str_width - square_brackets_width
		if maxval == 0:
			max_bar_width = bar_space-3
			image = "    "
			if cols < min_columns:
				return image
			if position <= 0.5:
				offset = 2 * position
			else:
				offset = 2 * (1 - position)
			delta = 0.5 / max_bar_width
			position += delta
			if position >= 1.0:
				position = 0.0
			# make sure it touches the ends
			if 1.0 - position < delta:
				position = 1.0
			if position < 0.5 and 0.5 - position < delta:
				position = 0.5
			self._position = position
			bar_width = int(offset * max_bar_width)
			image = image + "[" + (bar_width * " ") + \
				"<=>" + ((max_bar_width - bar_width) * " ") + "]"
			return image
		else:
			percentage = int(100 * float(curval) / maxval)
			if percentage == 100:
				percentage_str_width += 1
				bar_space -= 1
			max_bar_width = bar_space - 1
			image = ("%d%% " % percentage).rjust(percentage_str_width)
			if cols < min_columns:
				return image
			offset = float(curval) / maxval
			bar_width = int(offset * max_bar_width)
			image = image + "[" + (bar_width * "=") + \
				">" + ((max_bar_width - bar_width) * " ") + "]"
			return image

try:
	_parse_color_map(onerror=lambda e: writemsg("%s\n" % str(e), noiselevel=-1))
except FileNotFound:
	pass
except PermissionDenied, e:
	writemsg("Permission denied: '%s'\n" % str(e), noiselevel=-1)
	del e
except PortageException, e:
	writemsg("%s\n" % str(e), noiselevel=-1)
	del e
