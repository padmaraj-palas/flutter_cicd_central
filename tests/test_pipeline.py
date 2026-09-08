"""Run the Jenkinsfile's Linux shell wrapper with Docker stubbed, not Jenkins."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHELL = shutil.which("sh")
if not SHELL and os.name == "nt":
    candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    if candidate.is_file():
        SHELL = str(candidate)


@unittest.skipUnless(SHELL, "A POSIX shell is required")
class LinuxWrapperTests(unittest.TestCase):
    def run_wrapper(self, action, platform):
        source = ROOT.joinpath("Jenkinsfile").read_text(encoding="utf-8")
        wrapper = source.split("def linuxRun(", 1)[1].split("def archiveOutput(", 1)[0]
        script = re.search(r"sh '''(.*?)'''", wrapper, re.S).group(1)
        env = os.environ.copy()
        env.pop("CI_ACTION", None)
        env.pop("CI_PLATFORM", None)
        env.update(WORKSPACE="/workspace/Flutter CI", CI_ROOT="/workspace/Flutter CI/ci-platform",
                   FLUTTER_IMAGE="flutter-ci:1.0", MSYS_NO_PATHCONV="1")
        if action is not None:
            env["CI_ACTION"] = action
        if platform is not None:
            env["CI_PLATFORM"] = platform
        return subprocess.run(
            [SHELL, "-c", 'docker() { printf "%s\\n" "$@"; }\n' + script],
            env=env, text=True, capture_output=True, timeout=10,
        )

    def test_optional_platform_and_build_arguments(self):
        for action, platform in [("validate", None), ("quality", None),
                                 ("validate", ""), ("quality", ""),
                                 ("build", "web"), ("build", "android")]:
            with self.subTest(action=action, platform=platform):
                result = self.run_wrapper(action, platform)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = result.stdout.splitlines()
                expected = ["python3", "/workspace/Flutter CI/ci-platform/scripts/build.py",
                            action, "--project", "/workspace/Flutter CI/app"]
                if platform:
                    expected += ["--platform", platform]
                self.assertEqual(args[args.index("python3"):], expected)

    def test_missing_required_action_still_fails(self):
        result = self.run_wrapper(None, None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CI_ACTION", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
