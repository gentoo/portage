# Copyright 2017-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools
import random

from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop

class CallSoonFifoTestCase(TestCase):

	def testCallSoonFifo(self):

		event_loop = global_event_loop()
		inputs = [random.random() for index in range(10)]
		outputs = []
		finished = event_loop.create_future()

		def add_output(value):
			outputs.append(value)
			if len(outputs) == len(inputs):
				finished.set_result(True)

		for value in inputs:
			event_loop.call_soon(functools.partial(add_output, value))

		event_loop.run_until_complete(finished)
		self.assertEqual(inputs, outputs)
