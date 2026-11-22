#!/usr/bin/env python3
"""release-tag: parse a release tag into unit, version, prerelease flag and
commit, and check the commit is reachable from the default branch.

Invoked by release-tag.sh.

Inputs (env): INPUT_TAG, INPUT_UNIT_NAMES, INPUT_DEFAULT_BRANCH, INPUT_COMMIT,
INPUT_WORKING_DIRECTORY.
Runner env: GITHUB_OUTPUT, GITHUB_STEP_SUMMARY (both optional).
"""

import os
import re
import subprocess
import sys
import uuid

# SemVer 2.0 without build metadata, optional `<unit>/` prefix (design,
# Block `release-tag`, step 1).
TAG_RE = re.compile(
    r"^(?:(?P<unit>[a-z0-9][a-z0-9-]*)/)?"
    r"v(?P<ver>(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?P<pre>(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?)$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

SINGLE_FORM = "vX.Y.Z[-pre] or <unit>/vX.Y.Z[-pre]"
MULTI_FORM = "<unit>/vX.Y.Z[-pre]"


class TagError(Exception):
    """Failure reported as one ::error:: line."""


def escape(value):
    """Escape a value for a workflow command message."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def parse_unit_names(raw):
    names = [n.strip() for n in raw.splitlines() if n.strip()]
    if not names:
        raise TagError("input 'unit-names' is empty")
    for n in names:
        if not NAME_RE.match(n):
            raise TagError("input 'unit-names' holds invalid unit name '%s'" % n)
    if len(set(names)) != len(names):
        raise TagError("input 'unit-names' holds duplicate unit names")
    return names


def parse_tag(tag, names):
    """Return (unit, version, prerelease) or raise TagError."""
    form = SINGLE_FORM if len(names) == 1 else MULTI_FORM
    if not tag:
        raise TagError("input 'tag' is empty, expected %s" % form)
    if "+" in tag:
        raise TagError("tag '%s': build metadata not allowed, expected %s" % (tag, form))
    m = TAG_RE.fullmatch(tag)
    if not m:
        raise TagError("tag '%s' does not match %s (SemVer 2.0, no leading zeros)" % (tag, form))
    unit = m.group("unit")
    if unit is None:
        if len(names) != 1:
            raise TagError("tag '%s' has no unit but the matrix declares %d units, expected %s"
                           % (tag, len(names), MULTI_FORM))
        unit = names[0]
    elif unit not in names:
        raise TagError("tag '%s': unit '%s' is not in the matrix (known: %s), expected %s"
                       % (tag, unit, ", ".join(names), form))
    return unit, m.group("ver"), m.group("pre") is not None


def git(cwd, *args, check=True):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise TagError("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc


def tag_commit(cwd, tag):
    """Commit the tag points at (annotated or lightweight), or None."""
    proc = git(cwd, "rev-parse", "--verify", "--quiet", "refs/tags/%s^{commit}" % tag, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def resolve_commit(cwd, tag, override):
    existing = tag_commit(cwd, tag)
    if not override:
        if existing is None:
            raise TagError("tag '%s' not found in the checkout (fetch tags, fetch-depth: 0)" % tag)
        return existing
    if not SHA_RE.match(override):
        raise TagError("input 'commit' must be a 40-character lower-case hex sha, got '%s'"
                       % override)
    if git(cwd, "cat-file", "-e", "%s^{commit}" % override, check=False).returncode != 0:
        raise TagError("input 'commit' %s is not a commit in the checkout" % override)
    if existing is not None and existing != override:
        raise TagError("tag '%s' exists and points at %s, not input 'commit' %s"
                       % (tag, existing, override))
    return override


def check_reachable(cwd, commit, branch):
    if not branch:
        raise TagError("input 'default-branch' is empty")
    if not BRANCH_RE.match(branch) or branch.startswith("-") or \
            git(cwd, "check-ref-format", "--branch", branch, check=False).returncode != 0:
        raise TagError("input 'default-branch' '%s' is not a valid branch name" % branch)
    ref = "refs/remotes/origin/%s" % branch
    if git(cwd, "rev-parse", "--verify", "--quiet", ref, check=False).returncode != 0:
        raise TagError("origin/%s not found in the checkout (fetch-depth: 0)" % branch)
    proc = git(cwd, "merge-base", "--is-ancestor", commit, "origin/%s" % branch, check=False)
    if proc.returncode == 1:
        raise TagError("commit %s is not reachable from origin/%s" % (commit, branch))
    if proc.returncode != 0:
        raise TagError("git merge-base --is-ancestor failed: %s" % proc.stderr.strip())


def resolve(env):
    wd = env.get("INPUT_WORKING_DIRECTORY", "") or "."
    tag = env.get("INPUT_TAG", "").strip()
    names = parse_unit_names(env.get("INPUT_UNIT_NAMES", ""))
    unit, version, prerelease = parse_tag(tag, names)
    if not os.path.isdir(wd):
        raise TagError("working-directory '%s' does not exist" % wd)
    if git(wd, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        raise TagError("repository is shallow. Set actions/checkout fetch-depth: 0.")
    commit = resolve_commit(wd, tag, env.get("INPUT_COMMIT", "").strip())
    check_reachable(wd, commit, env.get("INPUT_DEFAULT_BRANCH", "").strip())
    return {
        "tag": tag,
        "unit": unit,
        "version": version,
        "prerelease": "true" if prerelease else "false",
        "commit": commit,
    }


def write_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        print("%s=%s" % (name, value))
        return
    delim = "EOF_%s" % uuid.uuid4().hex
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("%s<<%s\n%s\n%s\n" % (name, delim, value, delim))


def write_summary(result):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("### release-tag\n\n| Tag | Unit | Version | Prerelease | Commit |\n"
                 "|---|---|---|---|---|\n| `%s` | `%s` | `%s` | %s | `%s` |\n\n"
                 % (result["tag"], result["unit"], result["version"],
                    result["prerelease"], result["commit"]))


def main():
    try:
        result = resolve(os.environ)
    except TagError as exc:
        print("::error::release-tag: %s" % escape(str(exc)))
        return 1
    for key in ("unit", "version", "prerelease", "commit"):
        write_output(key, result[key])
    write_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
