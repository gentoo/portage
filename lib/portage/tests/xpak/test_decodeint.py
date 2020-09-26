# xpak/test_decodeint.py
# Copyright 2006-2020 Gentoo Authors
# Portage Unit Testing Functionality

from portage.tests import TestCase
from portage.xpak import decodeint, encodeint

class testDecodeIntTestCase(TestCase):

	def testDecodeInt(self):

		for n in range(1000):
			self.assertEqual(decodeint(encodeint(n)), n)

		for n in (2 ** 32 - 1,):
			self.assertEqual(decodeint(encodeint(n)), n)
