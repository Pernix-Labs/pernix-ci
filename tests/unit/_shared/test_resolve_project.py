import os
import subprocess
import sys
import tempfile
import unittest

SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "..", "..", "actions", "_shared")
sys.path.insert(0, SHARED)

import resolve_project  # noqa: E402
from resolve_project import ResolveError, resolve  # noqa: E402


class ResolveProjectTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def touch(self, *names):
        for name in names:
            path = os.path.join(self.dir, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").close()

    def test_slnx_wins_over_sln_and_csproj(self):
        self.touch("App.slnx", "App.sln", "App.csproj")
        self.assertEqual(resolve(self.dir), "App.slnx")

    def test_sln_wins_over_csproj(self):
        self.touch("App.sln", "App.csproj")
        self.assertEqual(resolve(self.dir), "App.sln")

    def test_single_csproj(self):
        self.touch("App.csproj")
        self.assertEqual(resolve(self.dir), "App.csproj")

    def test_ambiguous_slnx_falls_through_to_single_sln(self):
        self.touch("A.slnx", "B.slnx", "App.sln")
        self.assertEqual(resolve(self.dir), "App.sln")

    def test_ambiguity_fails_and_lists_candidates(self):
        self.touch("A.slnx", "B.slnx")
        with self.assertRaises(ResolveError) as ctx:
            resolve(self.dir)
        msg = str(ctx.exception)
        self.assertIn("A.slnx", msg)
        self.assertIn("B.slnx", msg)
        self.assertIn("'project' input", msg)

    def test_nothing_found_fails(self):
        self.touch("README.md", "sub/App.csproj")
        with self.assertRaises(ResolveError) as ctx:
            resolve(self.dir)
        self.assertIn("'project' input", str(ctx.exception))

    def test_explicit_project_exists(self):
        self.touch("A.slnx", "B.slnx", "src/App/App.csproj")
        self.assertEqual(resolve(self.dir, "src/App/App.csproj"),
                         "src/App/App.csproj")

    def test_explicit_project_missing(self):
        self.touch("App.slnx")
        with self.assertRaises(ResolveError) as ctx:
            resolve(self.dir, "Missing.csproj")
        self.assertIn("Missing.csproj", str(ctx.exception))

    def test_cli_success_and_failure(self):
        self.touch("App.sln")
        script = os.path.join(SHARED, "resolve_project.py")
        ok = subprocess.run([sys.executable, "-I", script, self.dir, ""],
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(ok.stdout.strip(), "App.sln")
        bad = subprocess.run([sys.executable, "-I", script, self.dir, "X.csproj"],
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("X.csproj", bad.stderr)
        self.assertEqual(resolve_project.main(["x"]), 1)


if __name__ == "__main__":
    unittest.main()
