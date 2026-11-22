import contextlib
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "actions", "dotnet-build"))

import check_args  # noqa: E402
from check_args import FORBIDDEN_PROPERTIES, check  # noqa: E402

PROPERTY_SWITCHES = ("-p:", "/p:", "-property:", "/property:", "--property:")
PROPERTIES = (
    "TargetFramework", "TargetFrameworks", "TreatWarningsAsErrors",
    "MSBuildTreatWarningsAsErrors", "CodeAnalysisTreatWarningsAsErrors",
    "WarningsAsErrors", "WarningsNotAsErrors", "NoWarn", "WarningLevel",
    "NuGetAudit", "NuGetAuditMode", "NuGetAuditLevel",
)


class CheckArgsTest(unittest.TestCase):
    def assertRejected(self, *args):
        errors = check(list(args))
        self.assertTrue(errors, "expected rejection of %r" % (args,))
        return errors

    def assertAllowed(self, *args):
        self.assertEqual(check(list(args)), [], "expected %r allowed" % (args,))

    def test_property_list_matches_spec(self):
        self.assertEqual(FORBIDDEN_PROPERTIES, {p.lower() for p in PROPERTIES})

    def test_empty_allowed(self):
        self.assertAllowed()

    def test_allowed_properties(self):
        self.assertAllowed("-p:Version=1.2.3")
        self.assertAllowed("-p:ContinuousIntegrationBuild=true")
        self.assertAllowed("/p:Version=1.2.3;ContinuousIntegrationBuild=true")
        self.assertAllowed("--property:InformationalVersion=1.2.3+abc")
        self.assertAllowed("-p:NoWarnExtra=1")

    def test_allowed_switches(self):
        self.assertAllowed("--no-incremental")
        self.assertAllowed("-v", "minimal")
        self.assertAllowed("-flp:verbosity=detailed")
        self.assertAllowed("-errorlogger:x.dll")
        self.assertAllowed("--nologo")

    def test_forbidden_property_matrix(self):
        for switch in PROPERTY_SWITCHES:
            for prop in PROPERTIES:
                for name in (prop, prop.upper(), prop.lower()):
                    with self.subTest(switch=switch, name=name):
                        self.assertRejected("%s%s=x" % (switch, name))
                        self.assertRejected(switch.upper() + name + "=x")

    def test_forbidden_property_in_semicolon_list(self):
        self.assertRejected("-p:Version=1.2.3;NoWarn=CS0168")

    def test_forbidden_property_in_comma_list(self):
        self.assertRejected("-p:Version=1.2.3,TreatWarningsAsErrors=false")

    def test_forbidden_property_with_spaces_and_quotes(self):
        self.assertRejected("-p: NoWarn =CS0168")
        self.assertRejected('-p:"NoWarn=CS0168"')

    def test_bare_property_switch_checks_next_arg(self):
        self.assertRejected("-p", "NoWarn=CS0168")
        self.assertRejected("--property", "TargetFramework=net8.0")
        self.assertAllowed("-p", "Version=1.2.3")

    def test_framework_switches(self):
        for arg in ("-f", "-F", "--framework", "--FRAMEWORK", "-f:net8.0",
                    "--framework=net8.0"):
            with self.subTest(arg=arg):
                self.assertRejected(arg, "net8.0")

    def test_warning_switches(self):
        for stem in ("warnaserror", "warnnotaserror", "nowarn", "warnasmessage"):
            for prefix in ("-", "/", "--"):
                for suffix in ("", "-", "+", ":CS0168", "=CS0168"):
                    for arg in (prefix + stem + suffix,
                                prefix + stem.upper() + suffix):
                        with self.subTest(arg=arg):
                            self.assertRejected(arg)

    def test_warning_short_forms(self):
        for arg in ("-err", "/err", "-err:CS0168", "-noerr", "/NOERR:CS0168"):
            with self.subTest(arg=arg):
                self.assertRejected(arg)

    def test_response_file(self):
        self.assertRejected("@build.rsp")
        self.assertRejected("@/tmp/args")

    def test_error_names_argument(self):
        errors = check(["-p:Version=1", "-p:NoWarn=CS0168", "-warnaserror-"])
        self.assertEqual(len(errors), 2)
        self.assertIn("'-p:NoWarn=CS0168'", errors[0])
        self.assertIn("'-warnaserror-'", errors[1])

    def test_main_exit_codes(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(check_args.main(["check_args.py", "-p:Version=1"]), 0)
            self.assertEqual(
                check_args.main(["check_args.py", "-p:NoWarn=CS0168"]), 1)
        self.assertIn("-p:NoWarn=CS0168", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
