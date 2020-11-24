import unittest

from onion_layers import NumberedName, flocked, get_middle_number

class TestNumberedName(unittest.TestCase):
	def test_parse(self):

		nn = NumberedName.from_layer_name("outline01")

		self.assertEqual(nn.name, "outline")
		self.assertEqual(nn.num, 1)
		self.assertEqual(nn.is_mask, False)
		self.assertEqual(nn.width, 2)

		s = nn.to_string()

		self.assertEqual(s, "outline01")

	def test_parse_no_number(self):

		nn = NumberedName.from_layer_name("foo")

		self.assertEqual(nn.name, "foo")
		self.assertEqual(nn.num, None)
		self.assertEqual(nn.is_mask, False)
		self.assertEqual(nn.width, None)

		s = nn.to_string()

		self.assertEqual(s, "foo")

class TestGetMiddleNumber(unittest.TestCase):
	def test_basic(self):
		self.assertEqual(50, get_middle_number(0, 100))
		self.assertEqual(150, get_middle_number(100, 200))

		self.assertEqual(25, get_middle_number(0, 50))
		self.assertEqual(12, get_middle_number(0, 25))
		self.assertEqual(6, get_middle_number(0, 12))
		self.assertEqual(3, get_middle_number(0, 6))
		self.assertEqual(1, get_middle_number(0, 3))

		self.assertEqual(1, get_middle_number(0, 2))
		self.assertEqual(2, get_middle_number(1, 3))
		self.assertEqual(3, get_middle_number(2, 4))

		with self.assertRaises(ValueError):
			get_middle_number(0, 1)

		with self.assertRaises(ValueError):
			get_middle_number(1, 2)

		with self.assertRaises(ValueError):
			get_middle_number(2, 3)

		with self.assertRaises(ValueError):
			get_middle_number(1, 1)

	def test_one(self):
		for n in range(100):
			self.assertEqual(n+1, get_middle_number(n, n+2))


class TestFlocked(unittest.TestCase):
	def test_flock(self):
		with flocked():
			pass

if __name__ == "__main__":
	unittest.main(verbosity=2)
