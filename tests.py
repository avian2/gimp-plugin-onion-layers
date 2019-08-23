import unittest

from onion_layers import NumberedName, flocked

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


class TestFlocked(unittest.TestCase):
	def test_flock(self):
		with flocked():
			pass

if __name__ == "__main__":
	unittest.main(verbosity=2)
