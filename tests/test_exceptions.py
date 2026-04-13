"""Tests for exception classes."""

import unittest

from mudrex._exceptions import MudrexAPIError, MudrexError, MudrexRequestError


class TestMudrexAPIError(unittest.TestCase):

    def test_str_with_code(self):
        e = MudrexAPIError("Bad request", code=400)
        self.assertEqual(str(e), "[400] Bad request")

    def test_str_without_code(self):
        e = MudrexAPIError("Something failed")
        self.assertEqual(str(e), "Something failed")

    def test_attributes(self):
        e = MudrexAPIError("msg", code=500, response="resp_obj")
        self.assertEqual(e.message, "msg")
        self.assertEqual(e.code, 500)
        self.assertEqual(e.response, "resp_obj")

    def test_is_mudrex_error(self):
        e = MudrexAPIError("x")
        self.assertIsInstance(e, MudrexError)
        self.assertIsInstance(e, Exception)


class TestMudrexRequestError(unittest.TestCase):

    def test_attributes(self):
        orig = ConnectionError("conn")
        e = MudrexRequestError("Network fail", original_error=orig)
        self.assertEqual(e.message, "Network fail")
        self.assertEqual(e.original_error, orig)

    def test_is_mudrex_error(self):
        e = MudrexRequestError("x")
        self.assertIsInstance(e, MudrexError)


if __name__ == "__main__":
    unittest.main()
