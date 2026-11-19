"""Kernel sysfs boolean parameters have Y/N rather than decimal text."""
import unittest
from run_probe import parse_scalar


class ScalarTests(unittest.TestCase):
    def test_kernel_boolean_and_integer_parameters(self):
        self.assertEqual(parse_scalar('Y\n'),1)
        self.assertEqual(parse_scalar('N\n'),0)
        self.assertEqual(parse_scalar('0x20\n'),32)
        self.assertEqual(parse_scalar('17\n'),17)
        with self.assertRaises(ValueError):
            parse_scalar('maybe\n')


if __name__=='__main__':unittest.main()
