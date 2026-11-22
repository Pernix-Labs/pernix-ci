import contextlib
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "actions", "secret-scan"))

import report  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "gitleaks-report.json")


class RunMain(unittest.TestCase):
    """Runs report.main with temp GITHUB_OUTPUT / GITHUB_STEP_SUMMARY files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "output")
        self.summary = os.path.join(self.tmp.name, "summary")
        env = {"GITHUB_OUTPUT": self.out, "GITHUB_STEP_SUMMARY": self.summary}
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)

        def restore():
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.addCleanup(restore)

    def write(self, name, text):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def run_main(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = report.main(["report.py", *args])
        return code, buf.getvalue()

    def read(self, path):
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as fh:
            return fh.read()


class FindingsTest(RunMain):
    def test_findings_fail_with_count(self):
        code, log = self.run_main(FIXTURE, "range a..b")
        self.assertEqual(code, 1)
        self.assertEqual(self.read(self.out), "findings-count=2\n")
        self.assertIn("2 finding(s)", log)

    def test_annotations(self):
        _, log = self.run_main(FIXTURE)
        lines = log.splitlines()
        self.assertIn("::error file=config/app.env,line=3::gitleaks github-pat in 0123456789ab",
                      lines)
        self.assertIn("::error file=deploy/a%2Cb%3Ac|d.yml,line=12::gitleaks generic-api-key in fedcba987654",
                      lines)

    def test_summary_table(self):
        self.run_main(FIXTURE, "range a..b")
        text = self.read(self.summary)
        self.assertIn("Scanned: range a..b", text)
        self.assertIn("| Rule | File | Line | Commit | Fingerprint |", text)
        self.assertIn("| github-pat | config/app.env | 3 | 0123456789ab | "
                      "0123456789abcdef0123456789abcdef01234567:config/app.env:github-pat:3 |",
                      text)
        self.assertIn("deploy/a,b:c\\|d.yml", text)

    def test_redacted_fields_never_emitted(self):
        _, log = self.run_main(FIXTURE)
        for text in (log, self.read(self.summary), self.read(self.out)):
            self.assertNotIn("REDACTED", text)
            self.assertNotIn("GITHUB_TOKEN", text)

    def test_load_keeps_only_allowed_fields(self):
        for f in report.load(FIXTURE):
            self.assertEqual(set(f), set(report.FIELDS))


class NoFindingsTest(RunMain):
    def test_empty_report_passes(self):
        path = self.write("empty.json", "[]")
        code, log = self.run_main(path)
        self.assertEqual(code, 0)
        self.assertEqual(self.read(self.out), "findings-count=0\n")
        self.assertIn("No findings.", self.read(self.summary))
        self.assertNotIn("::error", log)


class FailClosedTest(RunMain):
    def assert_tool_error(self, path, needle):
        code, log = self.run_main(path)
        self.assertEqual(code, 1)
        self.assertIn("::error::secret-scan: ", log)
        self.assertIn(needle, log)
        self.assertEqual(self.read(self.out), "")

    def test_missing_report(self):
        self.assert_tool_error(os.path.join(self.tmp.name, "nope.json"), "not found")

    def test_invalid_json(self):
        self.assert_tool_error(self.write("bad.json", "{not json"), "unreadable")

    def test_not_array(self):
        self.assert_tool_error(self.write("obj.json", "{}"), "not a JSON array")

    def test_non_object_entry(self):
        self.assert_tool_error(self.write("list.json", "[1]"), "non-object entry")

    def test_usage(self):
        code, log = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("usage", log)


class EscapeTest(unittest.TestCase):
    def test_escape_data(self):
        self.assertEqual(report.escape_data("a%b\r\nc"), "a%25b%0D%0Ac")

    def test_escape_property(self):
        self.assertEqual(report.escape_property("a:b,c%"), "a%3Ab%2Cc%25")

    def test_missing_commit_and_line(self):
        f = {k: None for k in report.FIELDS}
        f.update(RuleID="r", File="x")
        self.assertEqual(report.annotation(f), "::error file=x::gitleaks r in unknown")


if __name__ == "__main__":
    unittest.main()
