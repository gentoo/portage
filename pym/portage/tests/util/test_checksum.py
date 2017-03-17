# Copyright 2011-2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase

from portage.checksum import checksum_str
from portage.exception import DigestException

class ChecksumTestCase(TestCase):
	text = b'Some test string used to check if the hash works'

	def test_md5(self):
		self.assertEqual(checksum_str(b'', 'MD5'),
				'd41d8cd98f00b204e9800998ecf8427e')
		self.assertEqual(checksum_str(self.text, 'MD5'),
				'094c3bf4732f59b39d577e9726f1e934')

	def test_sha1(self):
		self.assertEqual(checksum_str(b'', 'SHA1'),
				'da39a3ee5e6b4b0d3255bfef95601890afd80709')
		self.assertEqual(checksum_str(self.text, 'SHA1'),
				'5c572017d4e4d49e4aa03a2eda12dbb54a1e2e4f')

	def test_sha256(self):
		self.assertEqual(checksum_str(b'', 'SHA256'),
				'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
		self.assertEqual(checksum_str(self.text, 'SHA256'),
				'e3d4a1135181fe156d61455615bb6296198e8ca5b2f20ddeb85cb4cd27f62320')

	def test_sha512(self):
		self.assertEqual(checksum_str(b'', 'SHA512'),
				'cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce47d0d13c5d85f2b0ff8318d2877eec2f63b931bd47417a81a538327af927da3e')
		self.assertEqual(checksum_str(self.text, 'SHA512'),
				'c8eaa902d48a2c82c2185a92f1c8bab8115c63c8d7a9966a8e8e81b07abcb9762f4707a6b27075e9d720277ba9fec072a59840d6355dd2ee64681d8f39a50856')

	def test_rmd160(self):
		try:
			self.assertEqual(checksum_str(b'', 'RMD160'),
					'9c1185a5c5e9fc54612808977ee8f548b2258d31')
			self.assertEqual(checksum_str(self.text, 'RMD160'),
					'fc453174f63fc011d6f64abd2c45fb6a53c8239b')
		except DigestException:
			self.skipTest('RMD160 implementation not available')

	def test_whirlpool(self):
		try:
			self.assertEqual(checksum_str(b'', 'WHIRLPOOL'),
					'19fa61d75522a4669b44e39c1d2e1726c530232130d407f89afee0964997f7a73e83be698b288febcf88e3e03c4f0757ea8964e59b63d93708b138cc42a66eb3')
			self.assertEqual(checksum_str(self.text, 'WHIRLPOOL'),
					'8f556a079b87057f19e0880eed6d833e40c916f4b133196f6842281a2517873074d399832470c11ee251696b4844a10197714a069ba3e3415c8a4eced8f91b48')
		except DigestException:
			self.skipTest('WHIRLPOOL implementation not available')

	def test_blake2b(self):
		try:
			self.assertEqual(checksum_str(b'', 'BLAKE2B'),
					'786a02f742015903c6c6fd852552d272912f4740e15847618a86e217f71f5419d25e1031afee585313896444934eb04b903a685b1448b755d56f701afe9be2ce')
			self.assertEqual(checksum_str(self.text, 'BLAKE2B'),
					'84cb3c88838c7147bc9797c6525f812adcdcb40137f9c075963e3a3ed1fe06aaeeb4d2bb5589bad286864dc1aa834cfc4d66b8d7e4d4a246d91d45ce3a6eee43')
		except DigestException:
			self.skipTest('BLAKE2B implementation not available')

	def test_blake2s(self):
		try:
			self.assertEqual(checksum_str(b'', 'BLAKE2S'),
					'69217a3079908094e11121d042354a7c1f55b6482ca1a51e1b250dfd1ed0eef9')
			self.assertEqual(checksum_str(self.text, 'BLAKE2S'),
					'823ab2429f27690450efe888b0404d092fe2ee72a9bd63d5342c251b4dbb373d')
		except DigestException:
			self.skipTest('BLAKE2S implementation not available')

	def test_sha3_256(self):
		try:
			self.assertEqual(checksum_str(b'', 'SHA3_256'),
					'a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a')
			self.assertEqual(checksum_str(self.text, 'SHA3_256'),
					'932fc0498ebb865406f9b6606280939283aa8a148562e39fd095a5d22bdec5c6')
		except DigestException:
			self.skipTest('SHA3_256 implementation not available')

	def test_sha3_512(self):
		try:
			self.assertEqual(checksum_str(b'', 'SHA3_512'),
					'a69f73cca23a9ac5c8b567dc185a756e97c982164fe25859e0d1dcc1475c80a615b2123af1f5f94c11e3e9402c3ac558f500199d95b6d3e301758586281dcd26')
			self.assertEqual(checksum_str(self.text, 'SHA3_512'),
					'6634c004dc31822fa65c2f1e2e3bbf0cfa35085653cca1ca9ca42f8f3f13c908405e0b665918146181c9fc9a9d793fc05429d669c35a55517820dfaa071425ca')
		except DigestException:
			self.skipTest('SHA3_512 implementation not available')

	def test_streebog256(self):
		try:
			self.assertEqual(checksum_str(b'', 'STREEBOG256'),
					'3f539a213e97c802cc229d474c6aa32a825a360b2a933a949fd925208d9ce1bb')
			self.assertEqual(checksum_str(self.text, 'STREEBOG256'),
					'4992f1239c46f15b89e7b83ded4d83fb5966da3692788a4a1a6d118f78c08444')
		except DigestException:
			self.skipTest('STREEBOG256 implementation not available')

	def test_streebog512(self):
		try:
			self.assertEqual(checksum_str(b'', 'STREEBOG512'),
					'8e945da209aa869f0455928529bcae4679e9873ab707b55315f56ceb98bef0a7362f715528356ee83cda5f2aac4c6ad2ba3a715c1bcd81cb8e9f90bf4c1c1a8a')
			self.assertEqual(checksum_str(self.text, 'STREEBOG512'),
					'330f5c26437f4e22c0163c72b12e93b8c27202f0750627355bdee43a0e0b253c90fbf0a27adbe5414019ff01ed84b7b240a1da1cbe10fae3adffc39c2d87a51f')
		except DigestException:
			self.skipTest('STREEBOG512 implementation not available')
