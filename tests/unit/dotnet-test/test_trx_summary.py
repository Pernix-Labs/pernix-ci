import datetime
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..", "..")
sys.path.insert(0, os.path.join(ROOT, "actions", "dotnet-test"))

import trx_summary  # noqa: E402
from trx_summary import (  # noqa: E402
    TrxError, find_trx, outputs, parse_time, parse_trx, render, summarise,
)

SAMPLES = os.path.join(ROOT, "tests", "fixtures", "dotnet-test", "trx")
NS = "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"


def sample(name):
    return os.path.join(SAMPLES, name)


def synthetic_trx(counters, results=(), start=None, finish=None):
    attrs = " ".join('%s="%s"' % kv for kv in counters.items())
    times = ""
    if start:
        times = '<Times start="%s" finish="%s" />' % (start, finish)
    body = []
    for name, outcome, message in results:
        error = ""
        if message is not None:
            error = ("<Output><ErrorInfo><Message>%s</Message></ErrorInfo>"
                     "</Output>" % message)
        body.append('<UnitTestResult testName="%s" outcome="%s">%s'
                    '</UnitTestResult>' % (name, outcome, error))
    return ('<?xml version="1.0" encoding="utf-8"?>'
            '<TestRun xmlns="%s">%s<Results>%s</Results>'
            '<ResultSummary outcome="Completed"><Counters %s /></ResultSummary>'
            '</TestRun>' % (NS, times, "".join(body), attrs))


class RecordedSamplesTest(unittest.TestCase):
    def test_vstest(self):
        run = parse_trx(sample("vstest-failed.trx"))
        self.assertEqual((run["total"], run["passed"], run["failed"]), (3, 2, 1))
        self.assertEqual(len(run["failures"]), 1)
        name, stem, message = run["failures"][0]
        self.assertEqual(
            name, "Fixture.Vstest.Tests.ForceFailTests.FailsOnlyWhenForced")
        self.assertEqual(stem, "vstest-failed")
        self.assertIn("Assert.NotEqual() Failure", message)

    def test_vstest_offset_times(self):
        s = summarise([sample("vstest-failed.trx")])
        self.assertAlmostEqual(s["duration"].total_seconds(), 0.442284, places=5)

    def test_trxreport(self):
        run = parse_trx(sample("trxreport-failed.trx"))
        self.assertEqual((run["total"], run["passed"], run["failed"]), (3, 2, 1))
        self.assertEqual([f[0] for f in run["failures"]], ["FailsOnlyWhenForced"])
        self.assertIn("Expected values to differ", run["failures"][0][2])

    def test_xunit_native(self):
        run = parse_trx(sample("xunit-failed.trx"))
        self.assertEqual((run["total"], run["passed"], run["failed"]), (4, 3, 1))
        self.assertEqual(
            [f[0] for f in run["failures"]],
            ["Fixture.MtpXunit.Tests.ForceFailTests.FailsOnlyWhenForced"])

    def test_xunit_explicit_only_counts_as_skipped(self):
        s = summarise([sample("xunit-explicit.trx")])
        self.assertEqual(
            (s["total"], s["passed"], s["failed"], s["skipped"]), (1, 0, 0, 1))

    def test_run_totals_over_several_files(self):
        s = summarise([sample("xunit-failed.trx"), sample("xunit-explicit.trx")])
        self.assertEqual(outputs(s), {
            "passed-count": 3, "failed-count": 1, "skipped-count": 1,
            "total-count": 5, "trx-count": 2,
        })
        self.assertEqual(len(s["failures"]), 1)
        # max finish (19:53:59.871516) - min start (19:53:58.394347)
        self.assertAlmostEqual(s["duration"].total_seconds(), 1.477169, places=5)

    def test_all_samples_find(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        nested = os.path.join(tmp, "a", "b")
        os.makedirs(nested)
        shutil.copy(sample("vstest-failed.trx"), tmp)
        shutil.copy(sample("trxreport-failed.trx"), nested)
        with open(os.path.join(tmp, "notes.txt"), "w") as f:
            f.write("x")
        found = find_trx(tmp)
        self.assertEqual(len(found), 2)
        s = summarise(found)
        self.assertEqual((s["total"], s["failed"]), (6, 2))


class CountersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_failed_includes_error_timeout_aborted(self):
        path = self.write("r.trx", synthetic_trx(
            {"total": 10, "passed": 4, "failed": 1, "error": 1, "timeout": 1,
             "aborted": 1, "notExecuted": 2},
            results=[("t1", "Failed", "boom"), ("t2", "Error", None),
                     ("t3", "Timeout", "slow"), ("t4", "Aborted", "gone"),
                     ("t5", "Passed", None), ("t6", "NotExecuted", None)]))
        s = summarise([path])
        self.assertEqual((s["passed"], s["failed"], s["skipped"], s["total"]),
                         (4, 4, 2, 10))
        self.assertEqual([f[0] for f in s["failures"]], ["t1", "t2", "t3", "t4"])
        self.assertEqual(s["failures"][1], ("t2", "r", ""))

    def test_missing_counters_are_zero(self):
        path = self.write("r.trx", synthetic_trx({}))
        s = summarise([path])
        self.assertEqual((s["total"], s["passed"], s["failed"], s["skipped"]),
                         (0, 0, 0, 0))
        self.assertIsNone(s["duration"])

    def test_no_files(self):
        s = summarise([])
        self.assertEqual(outputs(s)["trx-count"], 0)
        self.assertEqual(outputs(s)["total-count"], 0)

    def test_unparseable_file(self):
        path = self.write("bad.trx", "<TestRun")
        with self.assertRaises(TrxError):
            parse_trx(path)

    def test_wrong_root(self):
        path = self.write("other.trx", "<testsuites />")
        with self.assertRaises(TrxError):
            parse_trx(path)


class RenderTest(unittest.TestCase):
    def test_totals_and_failed_table(self):
        s = summarise([sample("vstest-failed.trx")])
        text = render(s, "vstest")
        self.assertIn("| 2 | 1 | 0 | 3 | 0.4s | 1 |", text)
        self.assertIn("### Failed tests", text)
        self.assertIn("| Fixture.Vstest.Tests.ForceFailTests.FailsOnlyWhenForced"
                      " | vstest-failed | ", text)

    def test_no_failed_table_when_green(self):
        s = summarise([sample("xunit-explicit.trx")])
        text = render(s, "mtp", "xunit")
        self.assertIn("mtp (xunit TRX)", text)
        self.assertNotIn("Failed tests", text)

    def test_message_truncated_and_rows_capped(self):
        long = "x|" * 400
        s = {"trx": 1, "total": 250, "passed": 0, "failed": 250, "skipped": 0,
             "duration": None,
             "failures": [("t%d" % i, "r", long) for i in range(250)]}
        text = render(s)
        row = [line for line in text.splitlines() if line.startswith("| t0 |")][0]
        message = row.split(" | ", 2)[2]
        self.assertLessEqual(len(message.replace("\\|", "|")), 500 + 2)
        self.assertIn("…", message)
        self.assertEqual(
            len([line for line in text.splitlines() if line.startswith("| t")]),
            200)
        self.assertIn("50 more rows omitted", text)


class ParseTimeTest(unittest.TestCase):
    def test_formats(self):
        expected = datetime.datetime(2026, 11, 22, 19, 53, 58, 394347)
        self.assertEqual(parse_time("2026-11-22T19:53:58.3943470+00:00"), expected)
        self.assertEqual(parse_time("2026-11-22T21:53:58.394347+02:00"), expected)
        self.assertEqual(parse_time("2026-11-22T19:53:58.394347Z"), expected)
        self.assertEqual(parse_time("2026-11-22T19:53:58"),
                         expected.replace(microsecond=0))
        self.assertIsNone(parse_time("yesterday"))
        self.assertIsNone(parse_time(None))


class MainTest(unittest.TestCase):
    def test_writes_summary_and_outputs(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        rd = os.path.join(tmp, "rd")
        os.makedirs(rd)
        shutil.copy(sample("trxreport-failed.trx"), rd)
        summary = os.path.join(tmp, "summary.md")
        output = os.path.join(tmp, "output")
        env = {"GITHUB_STEP_SUMMARY": summary, "GITHUB_OUTPUT": output,
               "TEST_RUNNER": "mtp", "TRX_FORMAT": "mtp"}
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            self.assertEqual(trx_summary.main(["trx_summary.py", rd]), 0)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        with open(output) as f:
            self.assertEqual(f.read(), "passed-count=2\nfailed-count=1\n"
                             "skipped-count=0\ntotal-count=3\ntrx-count=1\n")
        with open(summary) as f:
            self.assertIn("FailsOnlyWhenForced", f.read())


if __name__ == "__main__":
    unittest.main()
