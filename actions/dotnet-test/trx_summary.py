#!/usr/bin/env python3
"""Summarise TRX files from a dotnet-test run.

Usage: trx_summary.py <results-directory>

Parses every *.trx below results-directory (TeamTest 2010 schema, written by
VSTest, Microsoft.Testing.Extensions.TrxReport, and xunit.v3 natively).
Writes markdown to GITHUB_STEP_SUMMARY and the outputs passed-count,
failed-count, skipped-count, total-count, trx-count to GITHUB_OUTPUT when
those variables are set, else prints both to stdout.
Counters: failed = failed + error + timeout + aborted,
skipped = total - passed - failed. Exits 1 on an unparseable TRX file.
"""

import datetime
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "_shared"))

import md  # noqa: E402

NS = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"
FAILED_COUNTERS = ("failed", "error", "timeout", "aborted")
FAILED_OUTCOMES = frozenset(("failed", "error", "timeout", "aborted"))
ROW_LIMIT = 200
_TIME = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")


class TrxError(Exception):
    pass


def parse_time(text):
    """Parse a TRX timestamp (fraction up to 7 digits, optional offset)."""
    m = _TIME.match((text or "").strip())
    if not m:
        return None
    base, frac, tz = m.groups()
    value = datetime.datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
    if frac:
        value += datetime.timedelta(microseconds=int((frac[1:] + "000000")[:6]))
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        digits = tz[1:].replace(":", "")
        value -= sign * datetime.timedelta(
            hours=int(digits[:2]), minutes=int(digits[2:]))
    return value


def _int(value):
    try:
        return int(value or 0)
    except ValueError:
        return 0


def find_trx(results_directory):
    found = []
    for root, dirs, files in os.walk(results_directory):
        dirs.sort()
        found.extend(os.path.join(root, f) for f in sorted(files)
                     if f.lower().endswith(".trx"))
    return found


def parse_trx(path):
    """Return dict(counters, start, finish, failures) for one TRX file."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        raise TrxError("failed to parse TRX %s: %s" % (path, e))
    if root.tag != NS + "TestRun":
        raise TrxError("%s is not a TeamTest 2010 TRX file (root %s)"
                       % (path, root.tag))
    counters = root.find("%sResultSummary/%sCounters" % (NS, NS))
    attrs = counters.attrib if counters is not None else {}
    times = root.find(NS + "Times")
    stem = os.path.splitext(os.path.basename(path))[0]
    failures = []
    for result in root.iter(NS + "UnitTestResult"):
        if result.get("outcome", "").lower() not in FAILED_OUTCOMES:
            continue
        message = result.find("%sOutput/%sErrorInfo/%sMessage" % (NS, NS, NS))
        failures.append((
            result.get("testName", ""),
            stem,
            message.text if message is not None and message.text else "",
        ))
    return {
        "total": _int(attrs.get("total")),
        "passed": _int(attrs.get("passed")),
        "failed": sum(_int(attrs.get(k)) for k in FAILED_COUNTERS),
        "start": parse_time(times.get("start")) if times is not None else None,
        "finish": parse_time(times.get("finish")) if times is not None else None,
        "failures": failures,
    }


def summarise(paths):
    total = passed = failed = 0
    starts, finishes, failures = [], [], []
    for path in paths:
        run = parse_trx(path)
        total += run["total"]
        passed += run["passed"]
        failed += run["failed"]
        if run["start"]:
            starts.append(run["start"])
        if run["finish"]:
            finishes.append(run["finish"])
        failures.extend(run["failures"])
    duration = None
    if starts and finishes:
        duration = max(finishes) - min(starts)
    return {
        "trx": len(paths),
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": max(total - passed - failed, 0),
        "duration": duration,
        "failures": failures,
    }


def format_duration(delta):
    if delta is None:
        return "n/a"
    return "%.1fs" % max(delta.total_seconds(), 0.0)


def render(s, runner="", trx_format=""):
    lines = ["## dotnet-test", ""]
    if runner:
        mode = runner if runner != "mtp" else "mtp (%s TRX)" % trx_format
        lines += ["Runner: `%s`" % mode, ""]
    lines += md.table(
        ["Passed", "Failed", "Skipped", "Total", "Duration", "TRX files"],
        [[s["passed"], s["failed"], s["skipped"], s["total"],
          format_duration(s["duration"]), s["trx"]]]).splitlines()
    if s["failures"]:
        lines += ["", "### Failed tests", ""]
        lines += md.table(["Test", "TRX", "Message"], s["failures"],
                          limit=ROW_LIMIT).splitlines()
    return "\n".join(lines) + "\n"


def outputs(s):
    return {
        "passed-count": s["passed"],
        "failed-count": s["failed"],
        "skipped-count": s["skipped"],
        "total-count": s["total"],
        "trx-count": s["trx"],
    }


def main(argv):
    if len(argv) != 2:
        print("usage: trx_summary.py <results-directory>", file=sys.stderr)
        return 1
    try:
        s = summarise(find_trx(argv[1]))
    except TrxError as e:
        print("::error::%s" % e)
        return 1
    text = render(s, os.environ.get("TEST_RUNNER", ""),
                  os.environ.get("TRX_FORMAT", ""))
    if s["trx"] == 0:
        text += "\nNo TRX files found in `%s`.\n" % md.cell(argv[1])
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    output_file = os.environ.get("GITHUB_OUTPUT")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    out = "".join("%s=%s\n" % kv for kv in outputs(s).items())
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(out)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
