import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "actions",
                                "nuget-deprecation-report"))

import report  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")
BASE = "/home/runner/work/app"


def fixture(name):
    return os.path.join(FIXTURES, name)


def load(name):
    with open(fixture(name), encoding="utf-8") as fh:
        return report.parse(fh.read(), 0)


class RunMain(unittest.TestCase):
    """Runs report.main with temp GITHUB_OUTPUT / GITHUB_STEP_SUMMARY files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "output")
        self.summary = os.path.join(self.tmp.name, "summary")
        self.stderr = os.path.join(self.tmp.name, "stderr")
        env = {"GITHUB_OUTPUT": self.out, "GITHUB_STEP_SUMMARY": self.summary}
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        cwd = os.getcwd()
        os.chdir(self.tmp.name)

        def restore():
            os.chdir(cwd)
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.addCleanup(restore)

    def write_stderr(self, text):
        with open(self.stderr, "w", encoding="utf-8") as fh:
            fh.write(text)

    def run_main(self, json_path, exit_code=0):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = report.main(["report.py", json_path, str(exit_code),
                                self.stderr, "app.slnx"])
        return code, buf.getvalue()

    def read(self, path):
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def outputs(self):
        return dict(line.split("=", 1)
                    for line in self.read(self.out).splitlines())


class NoneTest(RunMain):
    def test_none_passes_with_zero_count(self):
        code, log = self.run_main(fixture("none.json"))
        self.assertEqual(code, 0)
        self.assertEqual(self.outputs(), {"deprecated-count": "0"})
        self.assertIn("No deprecated packages.", self.read(self.summary))
        self.assertNotIn("::error", log)
        self.assertNotIn("::warning", log)


class DeprecatedTest(RunMain):
    def test_direct_and_transitive_pass_and_count(self):
        code, log = self.run_main(fixture("deprecated.json"))
        self.assertEqual(code, 0)
        self.assertEqual(self.outputs(), {"deprecated-count": "7"})
        self.assertNotIn("::error", log)

    def test_warning_only_for_direct_packages(self):
        _, log = self.run_main(fixture("deprecated.json"))
        self.assertEqual(log.count("::warning::"), 1)
        self.assertIn("::warning::nuget-deprecation-report: "
                      "Microsoft.Azure.ServiceBus 5.2.0 is deprecated (Legacy), "
                      "alternative: Azure.Messaging.ServiceBus >= 0.0.0", log)
        self.assertNotIn("Microsoft.Azure.Services.AppAuthentication", log)

    def test_summary_columns(self):
        rows = report.collect(load("deprecated.json"), BASE)
        summary = report.summary(rows, "app.slnx")
        self.assertIn("| Projects | TFMs | Package | Version | Reasons | "
                      "Alternative | Direct/transitive |", summary)
        self.assertIn("| src/Lib/Lib.csproj | net10.0 | "
                      "Microsoft.Azure.ServiceBus | 5.2.0 | Legacy | "
                      "Azure.Messaging.ServiceBus >= 0.0.0 | direct |", summary)
        self.assertIn("| src/Lib/Lib.csproj | net10.0 | "
                      "Microsoft.Azure.Services.AppAuthentication | 1.0.3 | "
                      "Legacy | Azure.Identity >= 0.0.0 | transitive |", summary)
        self.assertIn("Deprecated: 7 (direct 1, transitive 6)", summary)

    def test_alternative_absent(self):
        rows = report.collect(load("deprecated.json"), BASE)
        row = [r for r in rows if r["id"] == "Microsoft.IdentityModel.Tokens"][0]
        self.assertEqual(row["alternative"], "")
        self.assertIn("| Microsoft.IdentityModel.Tokens | 5.4.0 | Legacy | "
                      "none | transitive |", report.summary(rows))

    def test_direct_alternative_absent_warning(self):
        data = load("deprecated.json")
        top = data["projects"][0]["frameworks"][0]["topLevelPackages"][0]
        del top["alternativePackage"]
        top["deprecationReasons"] = ["Legacy", "CriticalBugs"]
        rows = report.collect(data, BASE)
        self.assertEqual(report.annotation(rows[0]),
                         "::warning::nuget-deprecation-report: "
                         "Microsoft.Azure.ServiceBus 5.2.0 is deprecated "
                         "(Legacy, CriticalBugs)")

    def test_rows_deduplicated_across_tfms_and_projects(self):
        data = load("deprecated.json")
        proj = data["projects"][0]
        fw = proj["frameworks"][0]
        fw8 = copy.deepcopy(fw)
        fw8["framework"] = "net8.0"
        proj["frameworks"].append(fw8)
        other = copy.deepcopy(proj)
        other["path"] = BASE + "/src/Api/Api.csproj"
        # In Api the direct package is only transitive: direct must win.
        f = other["frameworks"][0]
        f["transitivePackages"] += f.pop("topLevelPackages")
        data["projects"].append(other)
        rows = report.collect(data, BASE)
        self.assertEqual(len(rows), 7)
        bus = [r for r in rows if r["id"] == "Microsoft.Azure.ServiceBus"][0]
        self.assertTrue(bus["direct"])
        self.assertEqual(sorted(bus["tfms"]), ["net10.0", "net8.0"])
        self.assertEqual(sorted(bus["projects"]),
                         ["src/Api/Api.csproj", "src/Lib/Lib.csproj"])
        self.assertEqual(bus["reasons"], ["Legacy"])

    def test_same_id_different_versions_are_separate_rows(self):
        data = load("deprecated.json")
        fw = data["projects"][0]["frameworks"][0]
        pkg = copy.deepcopy(fw["topLevelPackages"][0])
        pkg["resolvedVersion"] = "4.1.0"
        fw["topLevelPackages"].append(pkg)
        rows = report.collect(data, BASE)
        self.assertEqual(len(rows), 8)


class NotRestoredTest(RunMain):
    def test_problems_no_assets_file_asks_for_restore(self):
        code, log = self.run_main(fixture("not-restored.json"), 1)
        self.assertEqual(code, 1)
        self.assertIn("run dotnet-restore first", log)
        self.assertEqual(self.read(self.out), "")

    def test_stderr_assets_hint_asks_for_restore(self):
        self.write_stderr("error: project.assets.json not found\n")
        code, log = self.run_main(fixture("malformed.json"), 1)
        self.assertEqual(code, 1)
        self.assertIn("run dotnet-restore first", log)


class FailClosedTest(RunMain):
    def test_malformed_json_fails(self):
        code, log = self.run_main(fixture("malformed.json"))
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", log)
        self.assertEqual(self.read(self.out), "")

    def test_nonzero_exit_fails_even_with_valid_json(self):
        self.write_stderr("error: unable to load the service index\n")
        code, log = self.run_main(fixture("none.json"), 1)
        self.assertEqual(code, 1)
        self.assertIn("exited with code 1", log)
        self.assertIn("service index", log)
        self.assertEqual(self.read(self.out), "")

    def test_problem_error_fails(self):
        with self.assertRaises(report.ReportError) as ctx:
            report.parse('{"problems": [{"level": "error", "text": "boom"}],'
                         ' "projects": []}', 0)
        self.assertIn("boom", str(ctx.exception))

    def test_missing_output_file_fails(self):
        code, log = self.run_main(os.path.join(self.tmp.name, "absent.json"))
        self.assertEqual(code, 1)
        self.assertIn("not found", log)

    def test_missing_projects_fails(self):
        with self.assertRaises(report.ReportError):
            report.parse('{"version": 1}', 0)

    def test_wrong_shape_fails(self):
        doc = json.dumps({"projects": [{"frameworks": [
            {"framework": "net10.0", "topLevelPackages": {}}]}]})
        with self.assertRaises(report.ReportError):
            report.collect(report.parse(doc, 0), BASE)


if __name__ == "__main__":
    unittest.main()
