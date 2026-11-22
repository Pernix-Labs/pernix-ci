#!/usr/bin/env python3
"""Resolve the .NET project or solution a block operates on.

Usage: resolve_project.py <working-directory> [project]

With a non-empty `project`, it must exist relative to `working-directory`.
Otherwise the top level of `working-directory` is searched: exactly one
*.slnx wins, else exactly one *.sln, else exactly one *.csproj.
Prints the resolved path relative to `working-directory`.
"""

import os
import sys

PRECEDENCE = (".slnx", ".sln", ".csproj")


class ResolveError(Exception):
    pass


def resolve(working_directory, project=""):
    if not os.path.isdir(working_directory):
        raise ResolveError(
            "working-directory '%s' does not exist" % working_directory
        )
    if project:
        if not os.path.exists(os.path.join(working_directory, project)):
            raise ResolveError(
                "project '%s' not found in working-directory '%s'"
                % (project, working_directory)
            )
        return project

    names = sorted(
        n for n in os.listdir(working_directory)
        if os.path.isfile(os.path.join(working_directory, n))
    )
    candidates = []
    for ext in PRECEDENCE:
        matches = [n for n in names if n.endswith(ext)]
        if len(matches) == 1:
            return matches[0]
        candidates.extend(matches)

    if candidates:
        detail = "ambiguous candidates: %s" % ", ".join(candidates)
    else:
        detail = "no *.slnx, *.sln or *.csproj found"
    raise ResolveError(
        "cannot auto-detect project in working-directory '%s' (%s); "
        "set the 'project' input" % (working_directory, detail)
    )


def main(argv):
    if len(argv) not in (2, 3):
        print("usage: resolve_project.py <working-directory> [project]",
              file=sys.stderr)
        return 1
    project = argv[2] if len(argv) == 3 else ""
    try:
        print(resolve(argv[1], project))
    except ResolveError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
