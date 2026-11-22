#!/usr/bin/env python3
"""Reject build-args that override caller TargetFramework, warning, or NuGetAudit settings.

Usage: check_args.py [arg ...]

Each argv element is one build-args line. Matching is case-insensitive.
Rejected (Req 8.2, 8.5, 1.11):
  - switches -f, --framework, and -warnaserror*, -warnnotaserror*, -nowarn*,
    -warnasmessage*, and the MSBuild short forms -err and -noerr, with any of
    the -, --, / prefixes;
  - response files @<path>, whose contents cannot be checked;
  - -p:, /p:, -property:, /property:, --property: whose ;- or ,-separated
    assignments name a forbidden property. A bare -p / --property takes its
    assignments from the next element.
Exits 1 and prints one error per rejected argument to stderr.
"""

import sys

FORBIDDEN_PROPERTIES = frozenset(p.lower() for p in (
    "TargetFramework",
    "TargetFrameworks",
    "TreatWarningsAsErrors",
    "MSBuildTreatWarningsAsErrors",
    "CodeAnalysisTreatWarningsAsErrors",
    "WarningsAsErrors",
    "WarningsNotAsErrors",
    "WarningsAsMessages",
    "MSBuildWarningsAsMessages",
    "NoWarn",
    "WarningLevel",
    "NuGetAudit",
    "NuGetAuditMode",
    "NuGetAuditLevel",
))

FRAMEWORK_SWITCHES = ("f", "framework")
WARNING_SWITCH_PREFIXES = ("warnaserror", "warnnotaserror", "nowarn", "warnasmessage")
# MSBuild short forms: -err is -warnAsError, -noerr is -warnNotAsError.
WARNING_SWITCH_ALIASES = ("err", "noerr")
PROPERTY_SWITCHES = ("p", "property")


def _split_switch(arg):
    """Return (name, value) for a -, -- or / switch, else None. name is lowercased."""
    for prefix in ("--", "-", "/"):
        if arg.startswith(prefix) and len(arg) > len(prefix):
            body = arg[len(prefix):]
            # Split at the earliest ':' or '=' so a value containing the
            # other separator cannot leak into the switch name.
            positions = [i for i in (body.find(":"), body.find("=")) if i >= 0]
            if positions:
                i = min(positions)
                return body[:i].lower(), body[i + 1:]
            return body.lower(), None
    return None


def _forbidden_assignments(value):
    hits = []
    for part in value.replace(",", ";").split(";"):
        name = part.split("=", 1)[0].strip().strip("\"'").lower()
        if name in FORBIDDEN_PROPERTIES:
            hits.append(name)
    return hits


def check(args):
    """Return a list of error messages, one per rejected argument."""
    errors = []
    pending_property = None
    for arg in args:
        if pending_property is not None:
            if _forbidden_assignments(arg):
                errors.append(
                    "build-args '%s %s' sets a forbidden property; caller "
                    "TargetFramework, warning, and NuGetAudit settings must "
                    "not be overridden" % (pending_property, arg))
            pending_property = None
            continue

        if arg.startswith("@"):
            errors.append(
                "build-args '%s' is a response file; response files are "
                "rejected because their contents cannot be checked" % arg)
            continue

        switch = _split_switch(arg)
        if switch is None:
            continue
        name, value = switch

        if name in FRAMEWORK_SWITCHES:
            errors.append(
                "build-args '%s' selects a target framework; the block builds "
                "every TargetFramework the caller declares" % arg)
        elif (name.startswith(WARNING_SWITCH_PREFIXES)
              or name in WARNING_SWITCH_ALIASES):
            errors.append(
                "build-args '%s' changes warning handling; caller warning "
                "settings must not be overridden" % arg)
        elif name in PROPERTY_SWITCHES:
            if value is None:
                pending_property = arg
            elif _forbidden_assignments(value):
                errors.append(
                    "build-args '%s' sets a forbidden property; caller "
                    "TargetFramework, warning, and NuGetAudit settings must "
                    "not be overridden" % arg)
    return errors


def main(argv):
    errors = check(argv[1:])
    for message in errors:
        print(message, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
