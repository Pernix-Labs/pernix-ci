import os
import subprocess
import sys
import tempfile
import unittest

SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "..", "..", "actions", "_shared")
sys.path.insert(0, SHARED)

from globaljson import GlobalJsonError, format_value, get, strip_jsonc  # noqa: E402

JSONC = """﻿{
  // line comment
  "sdk": {
    "version": "10.0.100", /* block
    comment */
    "rollForward": "latestFeature",
  },
  "test": {
    "runner": "Microsoft.Testing.Platform", // trailing comment
  },
  "url": "https://example.com/a//b",
  "pattern": "/* not a comment */",
  "quote": "say \\"hi\\" // still string,}",
  "list": [1, 2,],
}
"""


class GlobalJsonTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "global.json")

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_nested_key(self):
        self.write(JSONC)
        self.assertEqual(get(self.path, "test.runner"),
                         "Microsoft.Testing.Platform")
        self.assertEqual(get(self.path, "sdk.version"), "10.0.100")

    def test_comment_markers_inside_strings_kept(self):
        self.write(JSONC)
        self.assertEqual(get(self.path, "url"), "https://example.com/a//b")
        self.assertEqual(get(self.path, "pattern"), "/* not a comment */")
        self.assertEqual(get(self.path, "quote"), 'say "hi" // still string,}')

    def test_trailing_commas(self):
        self.write(JSONC)
        self.assertEqual(get(self.path, "list"), [1, 2])
        self.assertEqual(strip_jsonc('{"a": [1,\n ],\n}').replace(" ", ""),
                         '{"a":[1\n]\n}')

    def test_absent_key(self):
        self.write(JSONC)
        self.assertIsNone(get(self.path, "test.missing"))
        self.assertIsNone(get(self.path, "sdk.version.deeper"))

    def test_missing_file(self):
        self.assertIsNone(get(self.path, "sdk.version"))

    def test_parse_error_names_file(self):
        self.write('{"sdk": {"version": }')
        with self.assertRaises(GlobalJsonError) as ctx:
            get(self.path, "sdk.version")
        self.assertIn(self.path, str(ctx.exception))

    def test_unterminated_block_comment_is_parse_error(self):
        self.write('{"a": 1 /* oops')
        with self.assertRaises(GlobalJsonError):
            get(self.path, "a")

    def test_format_value(self):
        self.assertEqual(format_value(None), "")
        self.assertEqual(format_value(True), "true")
        self.assertEqual(format_value(3), "3")
        self.assertEqual(format_value({"a": 1}), '{"a":1}')

    def run_cli(self, *args):
        script = os.path.join(SHARED, "globaljson.py")
        return subprocess.run([sys.executable, "-I", script] + list(args),
                              capture_output=True, text=True)

    def test_cli(self):
        missing = self.run_cli(self.path, "sdk.version")
        self.assertEqual((missing.returncode, missing.stdout), (0, "\n"))
        self.write(JSONC)
        ok = self.run_cli(self.path, "test.runner")
        self.assertEqual((ok.returncode, ok.stdout),
                         (0, "Microsoft.Testing.Platform\n"))
        absent = self.run_cli(self.path, "nope")
        self.assertEqual((absent.returncode, absent.stdout), (0, "\n"))
        self.write("{bad")
        bad = self.run_cli(self.path, "sdk.version")
        self.assertEqual(bad.returncode, 1)
        self.assertIn(self.path, bad.stderr)


if __name__ == "__main__":
    unittest.main()
