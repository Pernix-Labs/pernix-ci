#!/usr/bin/env python3
"""Select the dotnet-test runner and, for MTP, the TRX report format.

Usage:
  select_runner.py runner <global-json-file>
      Prints `mtp` when global.json `test.runner` equals
      Microsoft.Testing.Platform (ignore case), else `vstest`.
  select_runner.py trx-format <working-directory> <auto|mtp|xunit>
      Prints `mtp` (--report-trx) or `xunit` (--report-xunit-trx).
      `auto` scans every project.assets.json below an `obj` directory under
      working-directory for
      MTP test projects (libraries include Microsoft.Testing.Platform/):
      all reference Microsoft.Testing.Extensions.TrxReport -> mtp, else all
      reference xunit.v3.core (or
      xunit.v3.core.mtp-v1/-v2) -> xunit, else error.
Exits 1 with a message on stderr when no answer can be given.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "_shared"))

import globaljson  # noqa: E402

MTP_RUNNER = "microsoft.testing.platform"
MTP_LIBRARY = "microsoft.testing.platform/"
TRXREPORT_LIBRARY = "microsoft.testing.extensions.trxreport/"
# xunit.v3 1.x-3.x ships xunit.v3.core, 4.x ships xunit.v3.core.mtp-v1/-v2.
XUNIT_LIBRARIES = ("xunit.v3.core/", "xunit.v3.core.mtp-")
FORMATS = ("mtp", "xunit")


class SelectError(Exception):
    pass


def select_runner(global_json_file):
    try:
        value = globaljson.get(global_json_file, "test.runner")
    except globaljson.GlobalJsonError as e:
        raise SelectError(str(e))
    if isinstance(value, str) and value.strip().lower() == MTP_RUNNER:
        return "mtp"
    return "vstest"


def find_assets(working_directory):
    """Return project.assets.json paths that sit below an `obj` directory."""
    found = []
    for root, dirs, files in os.walk(working_directory):
        dirs.sort()
        rel = os.path.relpath(root, working_directory)
        if "project.assets.json" in files and "obj" in rel.split(os.sep):
            found.append(os.path.join(root, "project.assets.json"))
    return found


def library_names(assets_path):
    try:
        with open(assets_path, encoding="utf-8-sig") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        raise SelectError("failed to read %s: %s" % (assets_path, e))
    libraries = doc.get("libraries") if isinstance(doc, dict) else None
    if not isinstance(libraries, dict):
        return []
    return [k.lower() for k in libraries]


def _has(names, prefixes):
    return any(n.startswith(prefixes) for n in names)


def select_trx_format(working_directory, requested="auto"):
    requested = (requested or "auto").strip().lower()
    if requested in FORMATS:
        return requested
    if requested != "auto":
        raise SelectError(
            "trx-format '%s' is invalid; use auto, mtp, or xunit" % requested)

    projects = []
    for path in find_assets(working_directory):
        names = library_names(path)
        if _has(names, MTP_LIBRARY):
            projects.append(names)
    if not projects:
        raise SelectError(
            "no MTP test projects found under '%s' (no obj/project.assets.json "
            "references Microsoft.Testing.Platform); restore first, or set "
            "trx-format" % working_directory)
    if all(_has(n, TRXREPORT_LIBRARY) for n in projects):
        return "mtp"
    if all(_has(n, XUNIT_LIBRARIES) for n in projects):
        return "xunit"
    raise SelectError(
        "MTP projects lack TRX support: reference "
        "Microsoft.Testing.Extensions.TrxReport or use xunit.v3, or set "
        "trx-format")


def main(argv):
    try:
        if len(argv) == 3 and argv[1] == "runner":
            print(select_runner(argv[2]))
        elif len(argv) == 4 and argv[1] == "trx-format":
            print(select_trx_format(argv[2], argv[3]))
        else:
            print("usage: select_runner.py runner <global-json-file> | "
                  "trx-format <working-directory> <auto|mtp|xunit>",
                  file=sys.stderr)
            return 1
    except SelectError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
