#!/usr/bin/env python3
"""Turn a gitleaks JSON report into annotations, a job summary and outputs.

Usage: report.py <gitleaks.json> [scope]

Reads only the RuleID, File, StartLine, Commit and Fingerprint fields of each
finding. The fields holding the leaked value are never read, so they cannot
reach logs, the summary or outputs.

Exit 0 when there are no findings, 1 on any finding or on an unreadable report.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "_shared"))

from md import table  # noqa: E402

FIELDS = ("RuleID", "File", "StartLine", "Commit", "Fingerprint")
HEADERS = ["Rule", "File", "Line", "Commit", "Fingerprint"]


class ReportError(Exception):
    pass


def load(path):
    """Return findings as dicts restricted to FIELDS."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise ReportError("gitleaks report not found: %s" % path)
    except (OSError, ValueError) as exc:
        raise ReportError("gitleaks report unreadable: %s (%s)" % (path, exc))
    if not isinstance(data, list):
        raise ReportError("gitleaks report is not a JSON array: %s" % path)
    findings = []
    for item in data:
        if not isinstance(item, dict):
            raise ReportError("gitleaks report has a non-object entry: %s" % path)
        findings.append({k: item.get(k) for k in FIELDS})
    return findings


def _text(value):
    return "" if value is None else str(value)


def escape_data(s):
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(s):
    return escape_data(s).replace(":", "%3A").replace(",", "%2C")


def short_commit(f):
    return _text(f["Commit"])[:12] or "unknown"


def annotation(f):
    props = ["file=" + escape_property(_text(f["File"]))]
    line = _text(f["StartLine"])
    if line:
        props.append("line=" + escape_property(line))
    msg = "gitleaks %s in %s" % (_text(f["RuleID"]), short_commit(f))
    return "::error %s::%s" % (",".join(props), escape_data(msg))


def summary(findings, scope=""):
    out = ["## secret-scan", ""]
    if scope:
        out += ["Scanned: %s" % scope, ""]
    if not findings:
        out += ["No findings.", ""]
        return "\n".join(out)
    out += ["**%d finding(s).** Values are redacted." % len(findings), ""]
    rows = [[_text(f["RuleID"]), _text(f["File"]), _text(f["StartLine"]),
             short_commit(f), _text(f["Fingerprint"])] for f in findings]
    return "\n".join(out) + table(HEADERS, rows) + "\n"


def _append(env, text):
    path = os.environ.get(env)
    if not path:
        raise ReportError("%s is not set" % env)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text)


def main(argv):
    if len(argv) not in (2, 3):
        print("::error::usage: report.py <gitleaks.json> [scope]")
        return 1
    scope = argv[2] if len(argv) == 3 else ""
    try:
        findings = load(argv[1])
        _append("GITHUB_STEP_SUMMARY", summary(findings, scope))
        _append("GITHUB_OUTPUT", "findings-count=%d\n" % len(findings))
    except ReportError as exc:
        print("::error::secret-scan: %s" % escape_data(str(exc)))
        return 1
    for f in findings:
        print(annotation(f))
    if findings:
        print("::error::secret-scan: %d finding(s). Rotate the leaked credential, "
              "then remove it from history or allowlist a false positive in "
              ".gitleaksignore (fingerprints are in the job summary)."
              % len(findings))
        return 1
    print("secret-scan: no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
