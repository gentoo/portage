# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import signal
import sys

from portage import _unicode_decode
from portage.output import bold, create_color_func


class UserQuery:
	"""The UserQuery class is used to prompt the user with a set of responses,
	as well as accepting and handling the responses."""

	def __init__(self, myopts):
		self.myopts = myopts

	def query(self, prompt, enter_invalid, responses=None, colours=None):
		"""Display a prompt and a set of responses, then waits for user input
		and check it against the responses. The first match is returned.

		An empty response will match the first value in the list of responses,
		unless enter_invalid is True. The input buffer is *not* cleared prior
		to the prompt!

		prompt: The String to display as a prompt.
		responses: a List of Strings with the acceptable responses.
		colours: a List of Functions taking and returning a String, used to
		process the responses for display. Typically these will be functions
		like red() but could be e.g. lambda x: "DisplayString".

		If responses is omitted, it defaults to ["Yes", "No"], [green, red].
		If only colours is omitted, it defaults to [bold, ...].

		Returns a member of the List responses. (If called without optional
		arguments, it returns "Yes" or "No".)

		KeyboardInterrupt is converted to SystemExit to avoid tracebacks being
		printed."""
		if responses is None:
			responses = ["Yes", "No"]
			colours = [
				create_color_func("PROMPT_CHOICE_DEFAULT"),
				create_color_func("PROMPT_CHOICE_OTHER")
			]
		elif colours is None:
			colours=[bold]
		colours=(colours*len(responses))[:len(responses)]
		responses = [_unicode_decode(x) for x in responses]
		if "--alert" in self.myopts:
			prompt = '\a' + prompt
		print(bold(prompt), end=' ')
		try:
			while True:
				try:
					response = input("[%s] " %
						"/".join([colours[i](responses[i])
						for i in range(len(responses))]))
				except UnicodeDecodeError as e:
					response = _unicode_decode(e.object).rstrip('\n')
				if response or not enter_invalid:
					for key in responses:
						# An empty response will match the
						# first value in responses.
						if response.upper()==key[:len(response)].upper():
							return key
				print("Sorry, response '%s' not understood." % response,
		  end=' ')
		except (EOFError, KeyboardInterrupt):
			print("Interrupted.")
			sys.exit(128 + signal.SIGINT)
