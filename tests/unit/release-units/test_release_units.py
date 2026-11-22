import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..", "..")
sys.path.insert(0, os.path.join(ROOT, "actions", "release-units"))

import release_units as ru  # noqa: E402

SAMPLES = os.path.join(ROOT, "tests", "fixtures", "release-units", "msbuild")

# SemVer 2.0 reference regex (semver.org).
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$")

# Recorded `dotnet msbuild` output of tests/fixtures/release-flow/repo, root
# rewritten to /repo.
SAMPLE_PATHS = {
    "/repo/src/Svc/Svc.csproj": "Svc.json",
    "/repo/src/Shared/Shared.csproj": "Shared.json",
    "/repo/src/Lib/Lib.csproj": "Lib.json",
    "/repo/tests/Lib.Tests/Lib.Tests.csproj": "Lib.Tests.json",
    "/repo/tests/Svc.Tests/Svc.Tests.csproj": "Svc.Tests.json",
}


class RecordedEvaluator:
    def __init__(self):
        self.calls = []

    def __call__(self, project):
        self.calls.append(project)
        with open(os.path.join(SAMPLES, SAMPLE_PATHS[project]), encoding="utf-8") as fh:
            return json.load(fh)


def evaluation(is_test="", mtp="", refs=(), packages=()):
    return {
        "Properties": {"IsTestProject": is_test, "IsTestingPlatformApplication": mtp},
        "Items": {
            "ProjectReference": [{"FullPath": r, "Identity": r} for r in refs],
            "PackageReference": [{"Identity": p} for p in packages],
        },
    }


class MatrixTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for path in ("src/Svc/Svc.csproj", "src/Svc/Dockerfile", "src/Lib/Lib.csproj",
                     "deploy/svc.conf", "src/Lib/readme.txt"):
            full = os.path.join(self.tmp.name, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w").close()

    def validate(self, units):
        return ru.validate_matrix({"units": units}, self.tmp.name)

    def problems(self, data):
        with self.assertRaises(ru.SchemaError) as ctx:
            ru.validate_matrix(data, self.tmp.name)
        return ctx.exception.problems

    def assertProblem(self, data, unit, key, fragment):
        problems = self.problems(data)
        for u, k, msg in problems:
            if u == unit and k == key and fragment in msg:
                return
        self.fail("no problem (%s, %s, ~%s) in %r" % (unit, key, fragment, problems))


class Schema(MatrixTestCase):
    def test_valid_matrix_defaults(self):
        units = self.validate([
            {"name": "svc", "image": {"project": "src/Svc/Svc.csproj",
                                      "dockerfile": "src/Svc/Dockerfile"},
             "extra-inputs": ["deploy/svc.conf", "deploy/*.conf"]},
            {"name": "lib", "packages": ["src/Lib/Lib.csproj"]},
        ])
        self.assertEqual(units[0]["image"], {"project": "src/Svc/Svc.csproj",
                                             "dockerfile": "src/Svc/Dockerfile",
                                             "context": ".", "name": "svc"})
        self.assertEqual(units[0]["extra-inputs"], ["deploy/svc.conf", "deploy/*.conf"])
        self.assertIsNone(units[1]["image"])
        self.assertEqual(units[1]["packages"], ["src/Lib/Lib.csproj"])

    def test_not_a_mapping(self):
        self.assertEqual(self.problems(["x"])[0][2], "file must be a mapping with key 'units'")
        self.assertEqual(self.problems(None)[0][2], "file must be a mapping with key 'units'")

    def test_unknown_top_level_key(self):
        self.assertProblem({"units": [{"name": "lib", "packages": ["src/Lib/Lib.csproj"]}],
                            "version-line": 1}, "-", "version-line", "unknown top-level key")

    def test_units_missing_or_empty(self):
        self.assertProblem({}, "-", "units", "non-empty list")
        self.assertProblem({"units": []}, "-", "units", "non-empty list")

    def test_unknown_unit_key(self):
        self.assertProblem({"units": [{"name": "lib", "packages": ["src/Lib/Lib.csproj"],
                                       "version-line": "1"}]},
                           "lib", "version-line", "unknown key")

    def test_unknown_image_key(self):
        self.assertProblem({"units": [{"name": "svc", "image": {
            "project": "src/Svc/Svc.csproj", "dockerfile": "src/Svc/Dockerfile", "tag": "x"}}]},
            "svc", "image.tag", "unknown key")

    def test_bad_names(self):
        for name in ("Svc", "-svc", "svc_1", "", 12, None):
            with self.subTest(name=name):
                self.assertProblem({"units": [{"name": name, "packages": ["src/Lib/Lib.csproj"]}]},
                                   "#1", "name", "must match")

    def test_invalid_name_does_not_report_default_image_name(self):
        problems = self.problems({"units": [{"name": "Bad", "image": {
            "project": "src/Svc/Svc.csproj", "dockerfile": "src/Svc/Dockerfile"}}]})
        self.assertEqual([k for _, k, _ in problems], ["name"])

    def test_duplicate_name(self):
        self.assertProblem({"units": [{"name": "lib", "packages": ["src/Lib/Lib.csproj"]},
                                      {"name": "lib", "packages": ["src/Lib/Lib.csproj"]}]},
                           "lib", "name", "duplicate")

    def test_neither_image_nor_packages(self):
        self.assertProblem({"units": [{"name": "lib"}]}, "lib", "-", "at least one of")

    def test_image_required_keys(self):
        self.assertProblem({"units": [{"name": "svc", "image": {}}]}, "svc", "image.project", "required")
        self.assertProblem({"units": [{"name": "svc", "image": {}}]}, "svc", "image.dockerfile", "required")

    def test_image_name_invalid(self):
        self.assertProblem({"units": [{"name": "svc", "image": {
            "project": "src/Svc/Svc.csproj", "dockerfile": "src/Svc/Dockerfile", "name": "Svc"}}]},
            "svc", "image.name", "must match")

    def test_missing_paths(self):
        self.assertProblem({"units": [{"name": "svc", "image": {
            "project": "src/Nope/Nope.csproj", "dockerfile": "src/Svc/Dockerfile"}}]},
            "svc", "image.project", "not found")
        self.assertProblem({"units": [{"name": "svc", "image": {
            "project": "src/Svc/Svc.csproj", "dockerfile": "Dockerfile"}}]},
            "svc", "image.dockerfile", "not found")
        self.assertProblem({"units": [{"name": "svc", "image": {
            "project": "src/Svc/Svc.csproj", "dockerfile": "src/Svc/Dockerfile", "context": "ctx"}}]},
            "svc", "image.context", "not found")
        self.assertProblem({"units": [{"name": "lib", "packages": ["src/Lib/Gone.csproj"]}]},
                           "lib", "packages[0]", "not found")
        self.assertProblem({"units": [{"name": "lib", "packages": ["src/Lib/Lib.csproj"],
                                       "extra-inputs": ["deploy/gone.sh"]}]},
                           "lib", "extra-inputs[0]", "not found")

    def test_packages_shape(self):
        self.assertProblem({"units": [{"name": "lib", "packages": []}]}, "lib", "packages", "non-empty")
        self.assertProblem({"units": [{"name": "lib", "packages": "src/Lib/Lib.csproj"}]},
                           "lib", "packages", "non-empty")
        self.assertProblem({"units": [{"name": "lib", "packages": ["src/Lib/readme.txt"]}]},
                           "lib", "packages[0]", ".csproj")

    def test_path_escapes_and_magic(self):
        cases = [("../x.csproj", "'..'"), ("/abs/x.csproj", "relative"),
                 ("src/../../x.csproj", "'..'"), (":(glob)src/**", "pathspec magic")]
        for value, fragment in cases:
            with self.subTest(value=value):
                self.assertProblem({"units": [{"name": "lib", "packages": ["src/Lib/Lib.csproj"],
                                               "extra-inputs": [value]}]},
                                   "lib", "extra-inputs[0]", fragment)
                self.assertProblem({"units": [{"name": "lib", "packages": [value]}]},
                                   "lib", "packages[0]", fragment)

    def test_trailing_newline_rejected(self):
        self.assertProblem({"units": [{"name": "svc\n", "packages": ["src/Lib/Lib.csproj"]}]},
                           "#1", "name", "must match")
        self.assertProblem({"units": [{"name": "svc", "image": {
            "project": "src/Svc/Svc.csproj", "dockerfile": "src/Svc/Dockerfile", "name": "svc\n"}}]},
            "svc", "image.name", "must match")

    def test_extra_inputs_repo_root_rejected(self):
        for value in (".", "./", "src/.."):
            with self.subTest(value=value):
                fragment = "'..'" if ".." in value else "below working-directory"
                self.assertProblem({"units": [{"name": "lib", "packages": ["src/Lib/Lib.csproj"],
                                               "extra-inputs": [value]}]},
                                   "lib", "extra-inputs[0]", fragment)
        self.assertProblem({"units": [{"name": "lib", "packages": ["src/Lib/Lib.csproj"],
                                       "extra-inputs": [""]}]},
                           "lib", "extra-inputs[0]", "non-empty string")

    def test_extra_inputs_empty(self):
        self.assertProblem({"units": [{"name": "lib", "packages": ["src/Lib/Lib.csproj"],
                                       "extra-inputs": []}]}, "lib", "extra-inputs", "non-empty")

    def test_all_problems_reported(self):
        problems = self.problems({"units": [{"name": "a", "foo": 1, "packages": []}, {"name": "b"}]})
        self.assertGreaterEqual(len(problems), 3)


class Pathspecs(unittest.TestCase):
    def test_project_dirs_ancestors_icase_excludes(self):
        specs = ru.build_pathspecs(["src/Svc", "src/Shared"], "")
        self.assertEqual(specs[:6], [
            ":(glob)src/Shared/**", ":(exclude,glob)src/Shared/**/bin/**",
            ":(exclude,glob)src/Shared/**/obj/**",
            ":(glob)src/Svc/**", ":(exclude,glob)src/Svc/**/bin/**",
            ":(exclude,glob)src/Svc/**/obj/**"])
        for a in ("", "src/", "src/Svc/", "src/Shared/"):
            for f in ("Directory.Build.props", "Directory.Build.targets",
                      "Directory.Packages.props", "global.json"):
                self.assertIn(":(literal)" + a + f, specs)
            self.assertIn(":(icase,literal)" + a + "nuget.config", specs)
        self.assertEqual(len(specs), len(set(specs)))
        # Root first, then by depth.
        self.assertEqual(specs[6], ":(literal)Directory.Build.props")

    def test_working_directory_prefix_image_and_extra_inputs(self):
        specs = ru.build_pathspecs(["mono/src/Svc"], "mono",
                                   {"dockerfile": "src/Svc/Dockerfile", "context": "."},
                                   ["deploy/svc.conf", "deploy/*.sh"])
        self.assertIn(":(literal)mono/Directory.Packages.props", specs)
        self.assertIn(":(literal)Directory.Packages.props", specs)
        self.assertEqual(specs[-4:], [":(literal)mono/src/Svc/Dockerfile",
                                      ":(literal)mono/.dockerignore",
                                      "mono/deploy/svc.conf", "mono/deploy/*.sh"])

    def test_image_context_subdir(self):
        specs = ru.build_pathspecs(["src/Svc"], "", {"dockerfile": "src/Svc/Dockerfile",
                                                      "context": "src"})
        self.assertIn(":(literal)src/.dockerignore", specs)

    def test_project_at_repo_root(self):
        specs = ru.build_pathspecs([""], "")
        self.assertEqual(specs[:3], [":(glob)**", ":(exclude,glob)**/bin/**",
                                     ":(exclude,glob)**/obj/**"])
        self.assertIn(":(literal)global.json", specs)

    def test_glob_metacharacters_escaped(self):
        specs = ru.build_pathspecs(["src/A[1]"], "")
        self.assertEqual(specs[0], ":(glob)src/A[[]1]/**")

    def test_ancestors(self):
        self.assertEqual(ru.ancestors("a/b/c"), ["a/b/c", "a/b", "a", ""])
        self.assertEqual(ru.ancestors(""), [""])


class GraphBfs(unittest.TestCase):
    def test_closure_from_recorded_samples(self):
        graph = ru.Graph(RecordedEvaluator())
        self.assertEqual(graph.closure(["/repo/src/Svc/Svc.csproj"]),
                         {"/repo/src/Svc/Svc.csproj", "/repo/src/Shared/Shared.csproj"})
        self.assertEqual(graph.closure(["/repo/tests/Lib.Tests/Lib.Tests.csproj"]),
                         {"/repo/tests/Lib.Tests/Lib.Tests.csproj", "/repo/src/Lib/Lib.csproj",
                          "/repo/src/Shared/Shared.csproj"})

    def test_memoised(self):
        evaluator = RecordedEvaluator()
        graph = ru.Graph(evaluator)
        graph.closure(["/repo/src/Svc/Svc.csproj", "/repo/src/Lib/Lib.csproj"])
        graph.closure(["/repo/tests/Lib.Tests/Lib.Tests.csproj"])
        self.assertEqual(sorted(evaluator.calls), sorted(set(evaluator.calls)))
        self.assertEqual(len(evaluator.calls), 4)

    def test_cycle_terminates(self):
        nodes = {"/a.csproj": evaluation(refs=["/b.csproj"]),
                 "/b.csproj": evaluation(refs=["/a.csproj"])}
        graph = ru.Graph(nodes.__getitem__)
        self.assertEqual(graph.closure(["/a.csproj"]), {"/a.csproj", "/b.csproj"})

    def test_unexpected_output(self):
        graph = ru.Graph(lambda p: {"Items": {"ProjectReference": [{"Identity": "x"}]}})
        with self.assertRaises(ru.ResolveError):
            graph.closure(["/a.csproj"])


class TestProjectDetection(unittest.TestCase):
    def test_recorded_samples(self):
        graph = ru.Graph(RecordedEvaluator())
        self.assertTrue(graph.is_test("/repo/tests/Lib.Tests/Lib.Tests.csproj"))
        self.assertTrue(graph.is_test("/repo/tests/Svc.Tests/Svc.Tests.csproj"))
        self.assertFalse(graph.is_test("/repo/src/Lib/Lib.csproj"))
        self.assertFalse(graph.is_test("/repo/src/Svc/Svc.csproj"))

    def test_properties(self):
        self.assertTrue(ru.parse_evaluation(evaluation(is_test="true"), "p")[0])
        self.assertTrue(ru.parse_evaluation(evaluation(is_test="True"), "p")[0])
        self.assertTrue(ru.parse_evaluation(evaluation(mtp="true"), "p")[0])
        self.assertFalse(ru.parse_evaluation(evaluation(is_test="false", mtp="false"), "p")[0])
        self.assertFalse(ru.parse_evaluation(evaluation(), "p")[0])

    def test_known_framework_packages(self):
        for pkg in ("Microsoft.NET.Test.Sdk", "xunit", "xunit.v3", "xunit.v3.mtp-v2",
                    "XUnit.V3.Core", "NUnit", "MSTest", "MSTest.TestFramework", "TUnit"):
            with self.subTest(pkg=pkg):
                self.assertTrue(ru.is_test_framework_package(pkg))
                self.assertTrue(ru.parse_evaluation(evaluation(packages=[pkg]), "p")[0])
        for pkg in ("xunit.abstractions", "xunit.runner.visualstudio", "NUnit3TestAdapter",
                    "MSTest.TestAdapter", "Microsoft.Testing.Extensions.TrxReport",
                    "TUnit.Assertions", "Newtonsoft.Json"):
            with self.subTest(pkg=pkg):
                self.assertFalse(ru.is_test_framework_package(pkg))

    def test_unit_test_projects_direct_reference_only(self):
        graph = ru.Graph(RecordedEvaluator())
        sln = list(SAMPLE_PATHS)
        lib = graph.closure(["/repo/src/Lib/Lib.csproj"])
        svc = graph.closure(["/repo/src/Svc/Svc.csproj"])
        self.assertEqual(ru.unit_test_projects(graph, sln, lib),
                         ["/repo/tests/Lib.Tests/Lib.Tests.csproj"])
        self.assertEqual(ru.unit_test_projects(graph, sln, svc),
                         ["/repo/tests/Svc.Tests/Svc.Tests.csproj"])

    def test_test_project_referencing_shared_belongs_to_both(self):
        nodes = {
            "/shared.csproj": evaluation(),
            "/lib.csproj": evaluation(refs=["/shared.csproj"]),
            "/svc.csproj": evaluation(refs=["/shared.csproj"]),
            "/shared.tests.csproj": evaluation(refs=["/shared.csproj"], packages=["xunit.v3"]),
        }
        graph = ru.Graph(nodes.__getitem__)
        for root in ("/lib.csproj", "/svc.csproj"):
            self.assertEqual(ru.unit_test_projects(graph, list(nodes), graph.closure([root])),
                             ["/shared.tests.csproj"])

    def test_sln_list_parsing(self):
        text = ("Project(s)\n----------\nsrc/Lib/Lib.csproj\nsrc\\Svc\\Svc.csproj\n"
                "tests/X.Tests/X.Tests.fsproj\n")
        self.assertEqual(ru.parse_sln_list(text, "/repo"),
                         ["/repo/src/Lib/Lib.csproj", "/repo/src/Svc/Svc.csproj",
                          "/repo/tests/X.Tests/X.Tests.fsproj"])


class CiVersion(unittest.TestCase):
    def test_format(self):
        sha = "4fde8ee650ae87bdaaa6a8eb997be7d3a19d583d"
        self.assertEqual(ru.ci_version(sha), "0.0.0-ci.g4fde8ee")

    def test_semver_valid_for_edge_shas(self):
        for sha in ("0123456" + "0" * 33, "0000000" + "a" * 33, "1234567" + "f" * 33,
                    "abcdef0" + "1" * 33, "f" * 40):
            with self.subTest(sha=sha):
                self.assertRegex(ru.ci_version(sha), SEMVER_RE)

    def test_rejects_non_sha(self):
        for sha in ("", "abc", "G" * 40, "0" * 39, "0" * 40 + "\n"):
            with self.assertRaises(ru.ResolveError):
                ru.ci_version(sha)


if __name__ == "__main__":
    unittest.main()
