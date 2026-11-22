import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..", "..")
sys.path.insert(0, os.path.join(ROOT, "actions", "release-tag"))

import release_tag as rt  # noqa: E402

MULTI = ["svc", "lib"]
SINGLE = ["svc"]


class ParseTagTests(unittest.TestCase):
    def test_valid(self):
        cases = [
            ("svc/v1.2.3", MULTI, ("svc", "1.2.3", False)),
            ("lib/v1.0.0-rc.1", MULTI, ("lib", "1.0.0-rc.1", True)),
            ("v1.2.3", SINGLE, ("svc", "1.2.3", False)),
            ("svc/v1.2.3", SINGLE, ("svc", "1.2.3", False)),
            ("svc/v0.0.1-selftest.123", MULTI, ("svc", "0.0.1-selftest.123", True)),
            ("svc/v10.20.30-alpha-1.0.x-y", MULTI, ("svc", "10.20.30-alpha-1.0.x-y", True)),
        ]
        for tag, names, want in cases:
            with self.subTest(tag=tag):
                self.assertEqual(rt.parse_tag(tag, names), want)

    def test_invalid(self):
        cases = [
            ("api/v1.2.3", MULTI, "unit 'api' is not in the matrix (known: svc, lib)"),
            ("v1.2.3", MULTI, "has no unit but the matrix declares 2 units"),
            ("svc/v1.2.3+build.1", MULTI, "build metadata not allowed"),
            ("v1.2.3+build", SINGLE, "build metadata not allowed"),
            ("svc/v01.2.3", MULTI, "does not match"),
            ("svc/v1.2.3-rc.01", MULTI, "does not match"),
            ("svc/1.2.3", MULTI, "does not match"),
            ("1.2.3", SINGLE, "does not match"),
            ("svc/v1.2", MULTI, "does not match"),
            ("Svc/v1.2.3", MULTI, "does not match"),
            ("svc/v1.2.3-", MULTI, "does not match"),
            ("svc/v1.2.3\n", MULTI, "does not match"),
            ("", MULTI, "input 'tag' is empty"),
        ]
        for tag, names, msg in cases:
            with self.subTest(tag=tag):
                with self.assertRaises(rt.TagError) as ctx:
                    rt.parse_tag(tag, names)
                self.assertIn(msg, str(ctx.exception))

    def test_expected_form_in_message(self):
        with self.assertRaises(rt.TagError) as ctx:
            rt.parse_tag("v1.2.3", MULTI)
        self.assertIn("expected <unit>/vX.Y.Z[-pre]", str(ctx.exception))
        with self.assertRaises(rt.TagError) as ctx:
            rt.parse_tag("x", SINGLE)
        self.assertIn("vX.Y.Z[-pre] or <unit>/vX.Y.Z[-pre]", str(ctx.exception))

    def test_unit_names(self):
        self.assertEqual(rt.parse_unit_names("svc\n lib \n\n"), MULTI)
        for raw, msg in (("", "empty"), ("svc\nBad", "invalid unit name"),
                         ("svc\nsvc", "duplicate")):
            with self.subTest(raw=raw):
                with self.assertRaises(rt.TagError) as ctx:
                    rt.parse_unit_names(raw)
                self.assertIn(msg, str(ctx.exception))

    def test_escape(self):
        self.assertEqual(rt.escape("a%b\r\nc"), "a%25b%0D%0Ac")


class GitTests(unittest.TestCase):
    """Scripted repo: bare origin + clone, annotated/lightweight/orphan tags."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"}
        out = subprocess.run(["bash", os.path.join(HERE, "selftest.sh"), "init", cls.tmp],
                             check=True, capture_output=True, text=True, env=env).stdout
        cls.sha = dict(line.split("=", 1) for line in out.split())
        cls.repo = os.path.join(cls.tmp, "repo")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def env(self, tag, names="svc\nlib", commit="", branch="main", wd=None):
        return {
            "INPUT_TAG": tag,
            "INPUT_UNIT_NAMES": names,
            "INPUT_COMMIT": commit,
            "INPUT_DEFAULT_BRANCH": branch,
            "INPUT_WORKING_DIRECTORY": wd or self.repo,
        }

    def fails(self, env, msg):
        with self.assertRaises(rt.TagError) as ctx:
            rt.resolve(env)
        self.assertIn(msg, str(ctx.exception))

    def test_annotated(self):
        r = rt.resolve(self.env("svc/v1.2.3"))
        self.assertEqual((r["unit"], r["version"], r["prerelease"], r["commit"]),
                         ("svc", "1.2.3", "false", self.sha["c1"]))

    def test_lightweight(self):
        r = rt.resolve(self.env("lib/v1.0.0-rc.1"))
        self.assertEqual((r["unit"], r["version"], r["prerelease"], r["commit"]),
                         ("lib", "1.0.0-rc.1", "true", self.sha["c2"]))

    def test_unreachable(self):
        self.fails(self.env("svc/v9.9.9"),
                   "commit %s is not reachable from origin/main" % self.sha["orphan"])

    def test_missing_tag(self):
        self.fails(self.env("svc/v2.0.0"), "tag 'svc/v2.0.0' not found")

    def test_commit_override(self):
        r = rt.resolve(self.env("svc/v0.0.1-selftest.1", commit=self.sha["c2"]))
        self.assertEqual(r["commit"], self.sha["c2"])

    def test_commit_override_matches_tag(self):
        r = rt.resolve(self.env("svc/v1.2.3", commit=self.sha["c1"]))
        self.assertEqual(r["commit"], self.sha["c1"])

    def test_commit_override_conflicts_with_tag(self):
        self.fails(self.env("svc/v1.2.3", commit=self.sha["c2"]),
                   "tag 'svc/v1.2.3' exists and points at %s" % self.sha["c1"])

    def test_commit_override_unreachable(self):
        self.fails(self.env("svc/v0.0.1-selftest.1", commit=self.sha["orphan"]),
                   "is not reachable from origin/main")

    def test_commit_override_invalid(self):
        self.fails(self.env("svc/v0.0.1", commit="abc"), "40-character")
        self.fails(self.env("svc/v0.0.1", commit="f" * 40), "is not a commit")

    def test_default_branch(self):
        self.fails(self.env("svc/v1.2.3", branch=""), "'default-branch' is empty")
        self.fails(self.env("svc/v1.2.3", branch="--all"), "not a valid branch name")
        self.fails(self.env("svc/v1.2.3", branch="dev"), "origin/dev not found")

    def test_shallow(self):
        shallow = os.path.join(self.tmp, "shallow")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--no-local",
                        os.path.join(self.tmp, "origin.git"), shallow], check=True)
        self.fails(self.env("svc/v1.2.3", wd=shallow), "repository is shallow")

    def test_main_outputs(self):
        out_path = os.path.join(self.tmp, "github_output")
        saved = dict(os.environ)
        try:
            os.environ.update(self.env("v1.2.3", names="svc", commit=self.sha["c1"]))
            os.environ["GITHUB_OUTPUT"] = out_path
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            self.assertEqual(rt.main(), 0)
        finally:
            os.environ.clear()
            os.environ.update(saved)
        with open(out_path, encoding="utf-8") as fh:
            text = fh.read()
        for key, value in (("unit", "svc"), ("version", "1.2.3"), ("prerelease", "false")):
            self.assertRegex(text, r"(?m)^%s<<(EOF_\w+)\n%s\n\1$" % (key, value))

    def test_main_error_line(self):
        saved = dict(os.environ)
        buf = io.StringIO()
        try:
            os.environ.update(self.env("svc/v1.2.3+b"))
            with contextlib.redirect_stdout(buf):
                self.assertEqual(rt.main(), 1)
        finally:
            os.environ.clear()
            os.environ.update(saved)
        self.assertTrue(buf.getvalue().startswith(
            "::error::release-tag: tag 'svc/v1.2.3+b': build metadata not allowed"))


if __name__ == "__main__":
    unittest.main()
