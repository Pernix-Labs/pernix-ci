import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..", "..")
sys.path.insert(0, os.path.join(ROOT, "actions", "dotnet-test"))

from select_runner import (  # noqa: E402
    SelectError, find_assets, select_runner, select_trx_format,
)

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "dotnet-test")

MTP = "Microsoft.Testing.Platform/2.5.3"
TRXREPORT = "Microsoft.Testing.Extensions.TrxReport/2.5.3"
XUNIT_CORE = "xunit.v3.core/3.2.0"
XUNIT_CORE_MTP2 = "xunit.v3.core.mtp-v2/4.0.3"
MSTEST = "MSTest.TestFramework/4.5.3"


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, text):
        path = os.path.join(self.tmp.name, "global.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_absent_file_is_vstest(self):
        self.assertEqual(
            select_runner(os.path.join(self.tmp.name, "global.json")), "vstest")

    def test_absent_key_is_vstest(self):
        self.assertEqual(
            select_runner(self.write('{"sdk": {"version": "10.0.100"}}')),
            "vstest")

    def test_vstest_value_is_vstest(self):
        self.assertEqual(
            select_runner(self.write('{"test": {"runner": "VSTest"}}')),
            "vstest")

    def test_mtp(self):
        self.assertEqual(
            select_runner(self.write(
                '{"test": {"runner": "Microsoft.Testing.Platform"}}')),
            "mtp")

    def test_mtp_ignore_case(self):
        self.assertEqual(
            select_runner(self.write(
                '{"test": {"runner": "microsoft.testing.PLATFORM"}}')),
            "mtp")

    def test_jsonc(self):
        path = self.write(
            '{\n'
            '  // pinned SDK\n'
            '  "sdk": {"version": "10.0.100",},\n'
            '  /* runner */ "test": {"runner": "Microsoft.Testing.Platform",},\n'
            '}\n')
        self.assertEqual(select_runner(path), "mtp")

    def test_non_string_runner_is_vstest(self):
        self.assertEqual(
            select_runner(self.write('{"test": {"runner": 1}}')), "vstest")

    def test_parse_error_names_file(self):
        path = self.write('{"test": ')
        with self.assertRaises(SelectError) as ctx:
            select_runner(path)
        self.assertIn(path, str(ctx.exception))

    def test_fixture_global_json(self):
        self.assertEqual(
            select_runner(os.path.join(FIXTURES, "vstest", "global.json")),
            "vstest")
        for name in ("mtp-xunit", "mtp-trxreport"):
            self.assertEqual(
                select_runner(os.path.join(FIXTURES, name, "global.json")),
                "mtp", name)


class TrxFormatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.wd = self.tmp.name

    def project(self, name, *libraries, obj="obj"):
        obj_dir = os.path.join(self.wd, "tests", name, obj)
        os.makedirs(obj_dir)
        doc = {"version": 3, "libraries": {lib: {"type": "package"}
                                           for lib in libraries}}
        with open(os.path.join(obj_dir, "project.assets.json"), "w",
                  encoding="utf-8") as f:
            json.dump(doc, f)

    def test_explicit_formats_skip_scan(self):
        self.assertEqual(select_trx_format(self.wd, "mtp"), "mtp")
        self.assertEqual(select_trx_format(self.wd, "XUNIT"), "xunit")

    def test_invalid_format(self):
        with self.assertRaises(SelectError) as ctx:
            select_trx_format(self.wd, "junit")
        self.assertIn("trx-format", str(ctx.exception))

    def test_empty_set_says_restore_first(self):
        with self.assertRaises(SelectError) as ctx:
            select_trx_format(self.wd, "auto")
        self.assertIn("no MTP test projects found", str(ctx.exception))
        self.assertIn("restore first", str(ctx.exception))

    def test_non_mtp_projects_are_ignored(self):
        self.project("Lib", "Newtonsoft.Json/13.0.3")
        with self.assertRaises(SelectError) as ctx:
            select_trx_format(self.wd, "auto")
        self.assertIn("no MTP test projects found", str(ctx.exception))

    def test_all_trxreport_is_mtp(self):
        self.project("A", MTP, MSTEST, TRXREPORT)
        self.project("B", MTP, XUNIT_CORE_MTP2, TRXREPORT)
        self.project("Lib", "Newtonsoft.Json/13.0.3")
        self.assertEqual(select_trx_format(self.wd, "auto"), "mtp")

    def test_all_xunit_is_xunit(self):
        self.project("A", MTP, XUNIT_CORE)
        self.project("B", MTP, XUNIT_CORE_MTP2)
        self.assertEqual(select_trx_format(self.wd, ""), "xunit")

    def test_mixed_xunit_and_trxreport_is_xunit(self):
        self.project("A", MTP, XUNIT_CORE_MTP2, TRXREPORT)
        self.project("B", MTP, XUNIT_CORE_MTP2)
        self.assertEqual(select_trx_format(self.wd, "auto"), "xunit")

    def test_mstest_without_trxreport_errors(self):
        self.project("A", MTP, MSTEST)
        self.project("B", MTP, XUNIT_CORE)
        with self.assertRaises(SelectError) as ctx:
            select_trx_format(self.wd, "auto")
        message = str(ctx.exception)
        self.assertIn("Microsoft.Testing.Extensions.TrxReport", message)
        self.assertIn("xunit.v3", message)
        self.assertIn("trx-format", message)

    def test_xunit_v3_core_prefix_does_not_match_lookalike(self):
        self.project("A", MTP, "xunit.v3.core.extras/1.0.0")
        with self.assertRaises(SelectError):
            select_trx_format(self.wd, "auto")

    def test_assets_must_sit_below_obj(self):
        os.makedirs(os.path.join(self.wd, "elsewhere"))
        with open(os.path.join(self.wd, "elsewhere", "project.assets.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"libraries": {MTP: {}, XUNIT_CORE: {}}}, f)
        self.assertEqual(find_assets(self.wd), [])
        self.project("A", MTP, XUNIT_CORE, obj=os.path.join("obj", "custom"))
        self.assertEqual(len(find_assets(self.wd)), 1)

    def test_unreadable_assets_errors(self):
        obj_dir = os.path.join(self.wd, "A", "obj")
        os.makedirs(obj_dir)
        with open(os.path.join(obj_dir, "project.assets.json"), "w",
                  encoding="utf-8") as f:
            f.write("{not json")
        with self.assertRaises(SelectError):
            select_trx_format(self.wd, "auto")


if __name__ == "__main__":
    unittest.main()
