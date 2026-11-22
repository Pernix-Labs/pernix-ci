import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "actions", "_shared"))

from md import cell, table  # noqa: E402


class CellTest(unittest.TestCase):
    def test_escapes_pipe(self):
        self.assertEqual(cell("a|b"), "a\\|b")

    def test_newlines_become_br(self):
        self.assertEqual(cell("a\nb\r\nc\rd"), "a<br>b<br>c<br>d")

    def test_none_and_numbers(self):
        self.assertEqual(cell(None), "")
        self.assertEqual(cell(42), "42")

    def test_no_truncation_at_limit(self):
        self.assertEqual(cell("x" * 500), "x" * 500)

    def test_truncation(self):
        out = cell("x" * 501)
        self.assertEqual(len(out), 500)
        self.assertTrue(out.endswith("…"))
        self.assertEqual(cell("abcdef", max=4), "abc…")


class TableTest(unittest.TestCase):
    def test_basic(self):
        out = table(["A", "B"], [["1", "x|y"], ["2", "z"]])
        self.assertEqual(out, "| A | B |\n|---|---|\n| 1 | x\\|y |\n| 2 | z |\n")

    def test_empty_rows(self):
        self.assertEqual(table(["A"], []), "| A |\n|---|\n")

    def test_at_limit_no_note(self):
        out = table(["A"], [[i] for i in range(3)], limit=3)
        self.assertNotIn("omitted", out)
        self.assertEqual(out.count("\n| "), 3)

    def test_over_limit(self):
        out = table(["A"], [[i] for i in range(205)])
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("| ")]),
                         201)
        self.assertIn("5 more rows omitted", out)
        self.assertNotIn("| 200 |", out)

    def test_accepts_generator(self):
        out = table(["A"], ([i] for i in range(3)), limit=2)
        self.assertIn("1 more rows omitted", out)


if __name__ == "__main__":
    unittest.main()
