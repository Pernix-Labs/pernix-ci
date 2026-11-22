#!/usr/bin/env python3
"""Turn `dotnet list package --deprecated --format json` output into
annotations, a job summary and a `deprecated-count` output.

Usage: report.py <deprecated.json> <exit-code> <stderr-file> [project]

Fails closed: a non-zero `dotnet list` exit, an error in `problems[]` or
unparseable JSON fail the step instead of reporting zero. A missing assets
file fails with a hint to run dotnet-restore first.

Rows are unique on (package id, resolved version). Projects, target
frameworks and deprecation reasons of duplicate rows are merged. A row is
`direct` when the package is a top-level package in any project or framework.

Exit 0 whenever the report is produced: deprecations never fail the step.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "_shared"))

from md import table  # noqa: E402

NAME = "nuget-deprecation-report"
HEADERS = ["Projects", "TFMs", "Package", "Version", "Reasons", "Alternative",
           "Direct/transitive"]
NOT_RESTORED_MARKERS = ("no assets file", "project.assets.json")
RESTORE_HINT = "project is not restored: run dotnet-restore first"
STDERR_TAIL = 20


class ReportError(Exception):
    pass


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise ReportError("cannot read %s (%s)" % (path, exc))


def _tail(text, n=STDERR_TAIL):
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return "\n".join(lines[-n:])


def _not_restored(text):
    low = text.lower()
    return any(m in low for m in NOT_RESTORED_MARKERS)


def _with_stderr(msg, stderr):
    tail = _tail(stderr)
    return msg + ("\nstderr:\n" + tail if tail else "")


def _list(value, what):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ReportError("unexpected dotnet list output: %s is not an array"
                          % what)
    return value


def _obj(value, what):
    if not isinstance(value, dict):
        raise ReportError("unexpected dotnet list output: %s is not an object"
                          % what)
    return value


def parse(text, exit_code, stderr=""):
    """Validate the dotnet list result and return the parsed document."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        if _not_restored(text) or _not_restored(stderr):
            raise ReportError(RESTORE_HINT)
        raise ReportError(_with_stderr(
            "dotnet list output is not valid JSON (exit code %s, %s)"
            % (exit_code, exc), stderr))
    data = _obj(data, "document")

    errors = []
    for p in _list(data.get("problems"), "problems"):
        p = _obj(p, "problem")
        msg = str(p.get("text") or "")
        if _not_restored(msg):
            raise ReportError(RESTORE_HINT + " (%s)" % msg)
        if str(p.get("level") or "").lower() == "error":
            errors.append(msg or "unspecified error")
    if errors:
        raise ReportError("dotnet list reported error(s): " + "; ".join(errors))

    if exit_code != 0:
        if _not_restored(stderr):
            raise ReportError(RESTORE_HINT)
        raise ReportError(_with_stderr(
            "dotnet list exited with code %d" % exit_code, stderr))

    if "projects" not in data:
        raise ReportError("unexpected dotnet list output: no projects array")
    _list(data["projects"], "projects")
    return data


def _project_label(path, base):
    if not path:
        return "unknown"
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def _alternative(pkg):
    alt = pkg.get("alternativePackage")
    if alt is None:
        return ""
    alt = _obj(alt, "alternativePackage")
    alt_id = str(alt.get("id") or "")
    rng = str(alt.get("versionRange") or "")
    return (alt_id + " " + rng).strip() if alt_id else ""


def collect(data, base=None):
    """Return unique deprecated-package rows sorted by package and version."""
    base = base or os.getcwd()
    rows = {}
    for proj in _list(data.get("projects"), "projects"):
        proj = _obj(proj, "project")
        label = _project_label(proj.get("path"), base)
        for fw in _list(proj.get("frameworks"), "frameworks"):
            fw = _obj(fw, "framework")
            tfm = str(fw.get("framework") or "unknown")
            for kind, direct in (("topLevelPackages", True),
                                 ("transitivePackages", False)):
                for pkg in _list(fw.get(kind), kind):
                    pkg = _obj(pkg, "package")
                    key = (str(pkg.get("id") or ""),
                           str(pkg.get("resolvedVersion") or ""))
                    row = rows.setdefault(key, {
                        "id": key[0], "version": key[1], "reasons": [],
                        "alternative": "", "direct": False,
                        "projects": [], "tfms": [],
                    })
                    for reason in _list(pkg.get("deprecationReasons"),
                                        "deprecationReasons"):
                        reason = str(reason)
                        if reason not in row["reasons"]:
                            row["reasons"].append(reason)
                    row["alternative"] = row["alternative"] or _alternative(pkg)
                    row["direct"] = row["direct"] or direct
                    if label not in row["projects"]:
                        row["projects"].append(label)
                    if tfm not in row["tfms"]:
                        row["tfms"].append(tfm)
    return sorted(rows.values(), key=lambda r: (r["id"].lower(), r["version"]))


def summary(rows, project=""):
    out = ["## " + NAME, ""]
    if project:
        out += ["Target: `%s`" % project, ""]
    if not rows:
        out += ["No deprecated packages.", ""]
        return "\n".join(out)
    direct = sum(1 for r in rows if r["direct"])
    out += ["Deprecated: %d (direct %d, transitive %d)"
            % (len(rows), direct, len(rows) - direct), ""]
    body = [[", ".join(r["projects"]), ", ".join(r["tfms"]), r["id"],
             r["version"], ", ".join(r["reasons"]) or "unspecified",
             r["alternative"] or "none",
             "direct" if r["direct"] else "transitive"]
            for r in rows]
    return "\n".join(out) + table(HEADERS, body) + "\n"


def escape_data(s):
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotation(r):
    msg = "%s: %s %s is deprecated (%s)" % (
        NAME, r["id"], r["version"], ", ".join(r["reasons"]) or "unspecified")
    if r["alternative"]:
        msg += ", alternative: " + r["alternative"]
    return "::warning::%s" % escape_data(msg)


def _append(env, text):
    path = os.environ.get(env)
    if not path:
        raise ReportError("%s is not set" % env)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text)


def main(argv):
    if len(argv) not in (4, 5):
        print("::error::usage: report.py <deprecated.json> <exit-code> "
              "<stderr-file> [project]")
        return 1
    project = argv[4] if len(argv) == 5 else ""
    try:
        try:
            exit_code = int(argv[2])
        except ValueError:
            raise ReportError("invalid exit code '%s'" % argv[2])
        if not os.path.exists(argv[1]):
            raise ReportError(_with_stderr(
                "dotnet list output not found: %s" % argv[1], _read(argv[3])))
        data = parse(_read(argv[1]), exit_code, _read(argv[3]))
        rows = collect(data)
        _append("GITHUB_STEP_SUMMARY", summary(rows, project))
        _append("GITHUB_OUTPUT", "deprecated-count=%d\n" % len(rows))
    except ReportError as exc:
        print("::error::%s: %s" % (NAME, escape_data(str(exc))))
        return 1
    for r in rows:
        if r["direct"]:
            print(annotation(r))
    print("%s: %d deprecated package(s), %d direct"
          % (NAME, len(rows), sum(1 for r in rows if r["direct"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
