#!/usr/bin/env python3
"""release-units: validate the release-unit matrix, resolve each unit's MSBuild
project closure and input pathspecs, compute the last-touch sha, emit outputs.

Invoked by release-units.sh after yq converted the matrix file to JSON.

Usage: release_units.py <units-json-file>

Inputs (env): INPUT_UNITS_FILE, INPUT_WORKING_DIRECTORY, INPUT_SOLUTION,
INPUT_UNIT, INPUT_OWNER, INPUT_IMAGE_NAME_PREFIX.
Runner env: GITHUB_OUTPUT, GITHUB_STEP_SUMMARY (both optional).
"""

import json
import os
import posixpath
import re
import subprocess
import sys
import uuid

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
PREFIX_RE = re.compile(r"^[a-z0-9._-]*$")
PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PROJ_LINE_RE = re.compile(r"\.[A-Za-z]+proj$")

TOP_KEYS = ("units",)
UNIT_KEYS = ("name", "image", "packages", "extra-inputs")
IMAGE_KEYS = ("project", "dockerfile", "context", "name")
BUILD_FILES = ("Directory.Build.props", "Directory.Build.targets",
               "Directory.Packages.props", "global.json")

# Test-project detection (coordinator ruling O1). A project is a test project
# when MSBuild evaluation reports IsTestProject or IsTestingPlatformApplication
# as true, or it references one of these packages. Evaluation runs without
# restore, so package-imported properties are absent and the package list is
# what detects xunit.v3 / VSTest projects. NuGet ids are case-insensitive.
TEST_FRAMEWORK_PACKAGES = (
    "microsoft.net.test.sdk",
    "xunit",
    "xunit.v3*",
    "nunit",
    "mstest",
    "mstest.testframework",
    "tunit",
)


class ResolveError(Exception):
    """Failure reported as ::error:: lines."""


class SchemaError(ResolveError):
    """Matrix schema problems: list of (unit, key, message)."""

    def __init__(self, problems):
        ResolveError.__init__(self, "; ".join("unit %s: key %s: %s" % p for p in problems))
        self.problems = problems


# ---------------------------------------------------------------- helpers


def is_test_framework_package(package_id):
    pid = package_id.strip().lower()
    for entry in TEST_FRAMEWORK_PACKAGES:
        if entry.endswith("*"):
            if pid.startswith(entry[:-1]):
                return True
        elif pid == entry:
            return True
    return False


def ci_version(sha):
    """Commit-based CI version (Req 3.8). The 'g' prefix keeps the prerelease
    identifier alphanumeric, so an all-digit sha never yields a leading zero."""
    if not SHA_RE.match(sha):
        raise ResolveError("invalid commit sha '%s'" % sha)
    return "0.0.0-ci.g" + sha[:7]


def glob_escape(path):
    """Escape glob metacharacters for a :(glob) pathspec."""
    return re.sub(r"([*?\[])", r"[\1]", path)


def rel_join(*parts):
    """Join posix path parts, dropping empty and '.' parts."""
    kept = [p for p in parts if p not in ("", ".")]
    return posixpath.normpath(posixpath.join(*kept)) if kept else ""


def ancestors(rel_dir):
    """rel_dir and every ancestor up to the repo root (''), nearest first."""
    out = []
    cur = rel_dir
    while True:
        out.append(cur)
        if cur == "":
            return out
        cur = posixpath.dirname(cur)


def dedupe(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


# ---------------------------------------------------------------- schema


def validate_relative_path(value):
    """Return an error string for a path that is absolute, escapes upward,
    or uses pathspec magic. None when acceptable."""
    if not isinstance(value, str) or value.strip() == "":
        return "must be a non-empty string"
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
        return "must be relative, got '%s'" % value
    if value.startswith(":"):
        return "must not use pathspec magic, got '%s'" % value
    if ".." in re.split(r"[/\\]", value):
        return "must not contain '..', got '%s'" % value
    return None


def has_glob(value):
    return any(c in value for c in "*?[")


def validate_matrix(data, base_dir):
    """Validate the matrix JSON (design D4). base_dir is the absolute
    working-directory that all paths are relative to. Returns a list of
    normalised unit dicts. Raises ResolveError with all problems listed."""
    errors = []

    def err(unit, key, msg):
        errors.append((unit, key, msg))

    def check_path(unit, key, value, kind):
        problem = validate_relative_path(value)
        if problem:
            err(unit, key, problem)
            return None
        path = posixpath.normpath(value.replace("\\", "/"))
        full = os.path.join(base_dir, path)
        if kind == "file" and not os.path.isfile(full):
            err(unit, key, "file '%s' not found" % path)
        elif kind == "dir" and not os.path.isdir(full):
            err(unit, key, "directory '%s' not found" % path)
        elif kind == "any" and not os.path.exists(full):
            err(unit, key, "path '%s' not found" % path)
        return path

    def check_csproj(unit, key, value):
        path = check_path(unit, key, value, "file")
        if path is not None and not path.endswith(".csproj"):
            err(unit, key, "must be a .csproj path, got '%s'" % value)
        return path

    if not isinstance(data, dict):
        raise SchemaError([("-", "-", "file must be a mapping with key 'units'")])
    for key in data:
        if key not in TOP_KEYS:
            err("-", key, "unknown top-level key (allowed: units)")
    units = data.get("units")
    if not isinstance(units, list) or not units:
        err("-", "units", "must be a non-empty list")
        units = []

    seen = set()
    result = []
    for index, raw in enumerate(units):
        label = "#%d" % (index + 1)
        if not isinstance(raw, dict):
            err(label, "-", "unit must be a mapping")
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            err(label, "name", "must match ^[a-z0-9][a-z0-9-]*$, got %s" % json.dumps(name))
        else:
            label = name
            if name in seen:
                err(name, "name", "duplicate unit name")
            seen.add(name)
        for key in raw:
            if key not in UNIT_KEYS:
                err(label, key, "unknown key (allowed: %s)" % ", ".join(UNIT_KEYS))
        if "image" not in raw and "packages" not in raw:
            err(label, "-", "unit needs at least one of 'image' or 'packages'")

        unit = {"name": label, "image": None, "packages": [], "extra-inputs": []}

        if "image" in raw:
            image = raw["image"]
            if not isinstance(image, dict):
                err(label, "image", "must be a mapping")
            else:
                for key in image:
                    if key not in IMAGE_KEYS:
                        err(label, "image." + key,
                            "unknown key (allowed: %s)" % ", ".join(IMAGE_KEYS))
                for key in ("project", "dockerfile"):
                    if key not in image:
                        err(label, "image." + key, "required")
                project = check_csproj(label, "image.project", image["project"]) \
                    if "project" in image else None
                dockerfile = check_path(label, "image.dockerfile", image["dockerfile"], "file") \
                    if "dockerfile" in image else None
                context = check_path(label, "image.context", image.get("context", "."), "dir")
                image_name = image.get("name", label)
                if "name" in image and (not isinstance(image_name, str)
                                        or not PACKAGE_RE.match(image_name)):
                    err(label, "image.name",
                        "must match ^[a-z0-9][a-z0-9._-]*$, got %s" % json.dumps(image_name))
                unit["image"] = {"project": project, "dockerfile": dockerfile,
                                 "context": context, "name": image_name}

        if "packages" in raw:
            packages = raw["packages"]
            if not isinstance(packages, list) or not packages:
                err(label, "packages", "must be a non-empty list of .csproj paths")
            else:
                for i, value in enumerate(packages):
                    path = check_csproj(label, "packages[%d]" % i, value)
                    if path is not None:
                        unit["packages"].append(path)

        if "extra-inputs" in raw:
            extra = raw["extra-inputs"]
            if not isinstance(extra, list) or not extra:
                err(label, "extra-inputs", "must be a non-empty list of paths")
            else:
                for i, value in enumerate(extra):
                    key = "extra-inputs[%d]" % i
                    problem = validate_relative_path(value)
                    if problem:
                        err(label, key, problem)
                    elif has_glob(value):
                        unit["extra-inputs"].append(value)
                    else:
                        path = check_path(label, key, value, "any")
                        if path is not None:
                            unit["extra-inputs"].append(path)
        result.append(unit)

    if errors:
        raise SchemaError(errors)
    return result


# ---------------------------------------------------------------- graph


def parse_evaluation(data, project):
    """Parse `dotnet msbuild -getProperty -getItem` JSON for one project.
    Returns (is_test, [absolute ProjectReference paths])."""
    try:
        props = data.get("Properties", {})
        items = data.get("Items", {})
        refs = [ref["FullPath"] for ref in items.get("ProjectReference", [])]
        packages = [pkg["Identity"] for pkg in items.get("PackageReference", [])]
    except (AttributeError, KeyError, TypeError):
        raise ResolveError("unexpected MSBuild evaluation output for %s" % project)
    is_test = (
        str(props.get("IsTestProject", "")).lower() == "true"
        or str(props.get("IsTestingPlatformApplication", "")).lower() == "true"
        or any(is_test_framework_package(p) for p in packages)
    )
    return is_test, [os.path.normpath(r) for r in refs]


def dotnet_env():
    env = dict(os.environ)
    env.update({"DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1", "DOTNET_CLI_UI_LANGUAGE": "en"})
    return env


def msbuild_evaluate(project):
    """Evaluate one project with dotnet msbuild. Returns parsed JSON."""
    if not os.path.isfile(project):
        raise ResolveError("referenced project %s not found" % project)
    cmd = ["dotnet", "msbuild", project,
           "-getProperty:IsTestProject", "-getProperty:IsTestingPlatformApplication",
           "-getItem:ProjectReference", "-getItem:PackageReference"]
    try:
        proc = subprocess.run(cmd, cwd=os.path.dirname(project), env=dotnet_env(),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
    except FileNotFoundError:
        raise ResolveError("dotnet not found on PATH. Run actions/dotnet-setup first.")
    if proc.returncode != 0:
        tail = " | ".join((proc.stdout + proc.stderr).strip().splitlines()[-5:])
        raise ResolveError("MSBuild evaluation of %s failed (exit %d): %s. "
                           "Run actions/dotnet-setup first and check the project."
                           % (project, proc.returncode, tail))
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise ResolveError("MSBuild evaluation of %s returned non-JSON output" % project)


class Graph:
    """Memoised project graph. evaluator(abs_project) -> msbuild JSON."""

    def __init__(self, evaluator):
        self.evaluator = evaluator
        self.nodes = {}

    def node(self, project):
        project = os.path.normpath(project)
        if project not in self.nodes:
            self.nodes[project] = parse_evaluation(self.evaluator(project), project)
        return self.nodes[project]

    def is_test(self, project):
        return self.node(project)[0]

    def closure(self, roots):
        """BFS over ProjectReference. Returns the set of reachable projects."""
        seen = set()
        queue = [os.path.normpath(r) for r in roots]
        while queue:
            project = queue.pop(0)
            if project in seen:
                continue
            seen.add(project)
            queue.extend(r for r in self.node(project)[1] if r not in seen)
        return seen


def unit_test_projects(graph, solution_projects, unit_closure):
    """Test projects among solution_projects that directly reference a
    non-test project of unit_closure (Req 2.2). Direct only: a transitive
    match would attach every test project to every unit sharing a library
    (Svc.Tests -> Svc -> Shared would make Svc.Tests a lib test)."""
    targets = {p for p in unit_closure if not graph.is_test(p)}
    found = []
    for project in solution_projects:
        project = os.path.normpath(project)
        if project in targets or not graph.is_test(project):
            continue
        if set(graph.node(project)[1]) & targets:
            found.append(project)
    return sorted(found)


def parse_sln_list(text, solution_dir):
    """Absolute project paths from `dotnet sln list` output."""
    out = []
    for line in text.splitlines():
        line = line.strip().replace("\\", "/")
        if PROJ_LINE_RE.search(line):
            out.append(os.path.normpath(os.path.join(solution_dir, line)))
    return out


def solution_projects(solution):
    try:
        proc = subprocess.run(["dotnet", "sln", solution, "list"],
                              cwd=os.path.dirname(solution), env=dotnet_env(),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
    except FileNotFoundError:
        raise ResolveError("dotnet not found on PATH. Run actions/dotnet-setup first.")
    if proc.returncode != 0:
        tail = " | ".join((proc.stdout + proc.stderr).strip().splitlines()[-5:])
        raise ResolveError("dotnet sln %s list failed: %s" % (solution, tail))
    return parse_sln_list(proc.stdout, os.path.dirname(solution))


def find_solution(base_dir, given):
    if given:
        problem = validate_relative_path(given)
        if problem:
            raise ResolveError("input 'solution' %s" % problem)
        path = os.path.join(base_dir, given)
        if not os.path.isfile(path):
            raise ResolveError("solution '%s' not found in working-directory" % given)
        return path
    for ext in (".slnx", ".sln"):
        hits = sorted(f for f in os.listdir(base_dir) if f.endswith(ext))
        if len(hits) == 1:
            return os.path.join(base_dir, hits[0])
        if len(hits) > 1:
            raise ResolveError("multiple *%s files in working-directory (%s). Set input 'solution'."
                               % (ext, ", ".join(hits)))
    raise ResolveError("no *.slnx or *.sln in working-directory. Set input 'solution'.")


# ---------------------------------------------------------------- pathspecs


def build_pathspecs(project_dirs, wd_rel, image=None, extra_inputs=()):
    """Git pathspecs relative to the repo root (design step 5).

    project_dirs: closure project directories, relative to the repo root.
    wd_rel: working-directory relative to the repo root ('' for root).
    image: {'dockerfile', 'context'} relative to working-directory, or None.
    extra_inputs: unit extra-inputs relative to working-directory.
    """
    specs = []
    for d in sorted(set(project_dirs)):
        base = glob_escape(d) + "/" if d else ""
        specs.append(":(glob)%s**" % base)
        specs.append(":(exclude,glob)%s**/bin/**" % base)
        specs.append(":(exclude,glob)%s**/obj/**" % base)
    dirs = set()
    for d in project_dirs:
        dirs.update(ancestors(d))
    for a in sorted(dirs, key=lambda x: (x.count("/") if x else -1, x)):
        for f in BUILD_FILES:
            specs.append(":(literal)" + rel_join(a, f))
        specs.append(":(icase,literal)" + rel_join(a, "nuget.config"))
    if image:
        specs.append(":(literal)" + rel_join(wd_rel, image["dockerfile"]))
        specs.append(":(literal)" + rel_join(wd_rel, image["context"], ".dockerignore"))
    for e in extra_inputs:
        specs.append(rel_join(wd_rel, e))
    return dedupe(specs)


# ---------------------------------------------------------------- git


def git(repo, *args):
    proc = subprocess.run(["git", "-C", repo] + list(args),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)
    if proc.returncode != 0:
        raise ResolveError("git %s failed: %s" % (" ".join(args[:2]), proc.stderr.strip()))
    return proc.stdout.strip()


def last_touch(repo_root, pathspecs):
    sha = git(repo_root, "log", "-1", "--format=%H", "HEAD", "--", *pathspecs)
    if not sha:
        raise ResolveError("no commit reachable from HEAD touches the unit inputs")
    return sha


# ---------------------------------------------------------------- outputs


def write_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        print("%s=%s" % (name, value))
        return
    with open(path, "a", encoding="utf-8") as fh:
        if "\n" in value:
            delim = "ghadelimiter_" + uuid.uuid4().hex
            fh.write("%s<<%s\n%s\n%s\n" % (name, delim, value, delim))
        else:
            fh.write("%s=%s\n" % (name, value))


def write_summary(units):
    lines = ["## release-units", "",
             "| Unit | Kinds | Last-touch sha | Inputs | Test projects |",
             "|---|---|---|---|---|"]
    for u in units:
        lines.append("| %s | %s | `%s` | %d | %s |" % (
            u["name"], ", ".join(u["kinds"]), u["last-touch-sha"], len(u["inputs"]),
            "<br>".join("`%s`" % t for t in u["test-projects"]) or "none"))
    text = "\n".join(lines) + "\n"
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


# ---------------------------------------------------------------- main


def to_rel(path, base):
    rel = os.path.relpath(path, base).replace(os.sep, "/")
    return "" if rel == "." else rel


def resolve(env, units_json, evaluator=msbuild_evaluate, sln_lister=solution_projects):
    units_file = env.get("INPUT_UNITS_FILE", "") or ".github/release-units.yml"
    wd_input = env.get("INPUT_WORKING_DIRECTORY", "") or "."
    unit_filter = env.get("INPUT_UNIT", "").strip()
    owner = env.get("INPUT_OWNER", "").strip()
    prefix = env.get("INPUT_IMAGE_NAME_PREFIX", "").strip()

    if not os.path.isdir(wd_input):
        raise ResolveError("working-directory '%s' does not exist" % wd_input)
    base = os.path.realpath(wd_input)
    if git(base, "rev-parse", "--is-shallow-repository") == "true":
        raise ResolveError("repository is shallow. Set actions/checkout fetch-depth: 0.")
    root = os.path.realpath(git(base, "rev-parse", "--show-toplevel"))
    wd_rel = to_rel(base, root)

    units = validate_matrix(units_json, base)

    names = [u["name"] for u in units]
    if unit_filter:
        if unit_filter not in names:
            raise ResolveError("input 'unit' '%s' is not in %s (known: %s)"
                               % (unit_filter, units_file, ", ".join(names)))
        units = [u for u in units if u["name"] == unit_filter]

    if any(u["image"] for u in units):
        if not OWNER_RE.match(owner):
            raise ResolveError("input 'owner' must be a GitHub owner name, got '%s'" % owner)
        if not PREFIX_RE.match(prefix):
            raise ResolveError("input 'image-name-prefix' must match ^[a-z0-9._-]*$, got '%s'"
                               % prefix)

    solution = find_solution(base, env.get("INPUT_SOLUTION", "").strip())
    graph = Graph(evaluator)
    sln = sln_lister(solution)

    results = []
    for u in units:
        roots = list(u["packages"])
        if u["image"]:
            roots.insert(0, u["image"]["project"])
        closure = graph.closure([os.path.join(base, r) for r in roots])
        tests = unit_test_projects(graph, sln, closure)
        closure |= graph.closure(tests)
        for p in closure:
            if not (p + os.sep).startswith(root + os.sep):
                raise ResolveError("unit %s: project %s is outside the repository" % (u["name"], p))
        project_dirs = [to_rel(os.path.dirname(p), root) for p in closure]
        specs = build_pathspecs(project_dirs, wd_rel, u["image"], u["extra-inputs"])
        sha = last_touch(root, specs)
        projects = sorted(to_rel(p, base) for p in closure)
        test_rel = [to_rel(p, base) for p in tests]
        image = u["image"]
        package = (prefix + image["name"]) if image else ""
        if image and not PACKAGE_RE.match(package):
            raise ResolveError("unit %s: image package name '%s' is invalid" % (u["name"], package))
        results.append({
            "name": u["name"],
            "kinds": [k for k, on in (("image", bool(image)), ("packages", bool(u["packages"]))) if on],
            "last-touch-sha": sha,
            "ci-version": ci_version(sha),
            "image": "ghcr.io/%s/%s" % (owner.lower(), package) if image else "",
            "image-package": package,
            "image-project": image["project"] if image else "",
            "dockerfile": image["dockerfile"] if image else "",
            "context": image["context"] if image else "",
            "packages": u["packages"],
            "packages-list": "\n".join(u["packages"]),
            "projects": projects,
            "test-projects": test_rel,
            "projects-list": "\n".join(projects),
            "inputs": specs,
        })
    return results


def main(argv):
    if len(argv) != 2:
        print("usage: release_units.py <units-json-file>", file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except ValueError:
                raise ResolveError("%s must hold a single YAML document"
                                   % (os.environ.get("INPUT_UNITS_FILE") or "units-file"))
        units = resolve(os.environ, data)
    except SchemaError as exc:
        units_file = rel_join(os.environ.get("INPUT_WORKING_DIRECTORY", ""),
                              os.environ.get("INPUT_UNITS_FILE") or ".github/release-units.yml")
        for problem in exc.problems:
            print("::error file=%s::unit %s: key %s: %s" % ((units_file,) + tuple(problem)))
        return 1
    except ResolveError as exc:
        for line in str(exc).splitlines():
            print("::error::release-units: %s" % line)
        return 1
    write_output("units", json.dumps(units, separators=(",", ":")))
    write_output("unit-names", "\n".join(u["name"] for u in units))
    write_output("count", str(len(units)))
    write_summary(units)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
