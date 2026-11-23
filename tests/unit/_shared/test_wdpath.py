import os
import subprocess
import sys
import unittest

SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "..", "..", "actions", "_shared")
sys.path.insert(0, SHARED)

from wdpath import WdPathError, glob_prefix, join, normalize  # noqa: E402

SCRIPT = os.path.join(SHARED, "wdpath.py")


class NormalizeTest(unittest.TestCase):
    def test_cases(self):
        cases = {
            "": ".",
            ".": ".",
            "./": ".",
            "./.": ".",
            "src": "src",
            "./src": "src",
            "././src/": "src",
            "src/./app": "src/app",
            "src//app/": "src/app",
            "repo/.": "repo",
            "/abs/./x/": "/abs/x",
            "/": "/",
        }
        for given, want in cases.items():
            with self.subTest(given=given):
                self.assertEqual(normalize(given), want)

    def test_rejects_dotdot(self):
        for bad in ("..", "../x", "a/../b", "a/.."):
            with self.subTest(bad=bad), self.assertRaises(WdPathError):
                normalize(bad)


class JoinTest(unittest.TestCase):
    def test_cases(self):
        cases = {
            ("repo", "."): "repo",
            ("repo", ""): "repo",
            ("repo", "./"): "repo",
            ("repo", "./tests/fixtures/x"): "repo/tests/fixtures/x",
            ("repo", "tests/fixtures/x/"): "repo/tests/fixtures/x",
            ("repo", "/abs/x"): "/abs/x",
            ("", "./x"): "x",
            ("", "."): ".",
        }
        for (prefix, path), want in cases.items():
            with self.subTest(prefix=prefix, path=path):
                self.assertEqual(join(prefix, path), want)

    def test_rejects_dotdot(self):
        with self.assertRaises(WdPathError):
            join("repo", "../other")


class GlobPrefixTest(unittest.TestCase):
    def test_cases(self):
        cases = {
            ".": "",
            "": "",
            "./": "",
            "repo/.": "repo/",
            "./src": "src/",
            "src/app/": "src/app/",
            "/abs/x": "/abs/x/",
        }
        for given, want in cases.items():
            with self.subTest(given=given):
                self.assertEqual(glob_prefix(given), want)

    def test_no_dot_segments_in_pattern(self):
        for given in (".", "./", "repo/.", "./repo/./x", "repo//x"):
            pattern = glob_prefix(given) + "**/Directory.Packages.props"
            with self.subTest(given=given):
                self.assertNotIn("./", pattern)
                self.assertNotIn("//", pattern)
                self.assertFalse(pattern.startswith("/"))


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", SCRIPT, *args],
                              capture_output=True, text=True, check=False)

    def test_join(self):
        out = self.run_cli("join", "repo", ".")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "repo\n")

    def test_glob_dot_is_empty_line(self):
        out = self.run_cli("glob", ".")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "\n")

    def test_dotdot_fails_with_annotation(self):
        out = self.run_cli("join", "repo", "../x")
        self.assertEqual(out.returncode, 1)
        self.assertIn("::error::", out.stdout)

    def test_usage(self):
        self.assertEqual(self.run_cli("join", "repo").returncode, 2)


if __name__ == "__main__":
    unittest.main()
