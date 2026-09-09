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
                self.assertIn("ANDROID_ARTIFACT_TYPE", args)
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


@unittest.skipUnless(SHELL, "A POSIX shell is required")
class LinuxUploadWrapperTests(unittest.TestCase):
    def run_wrapper(self, action="upload", platform="android", docker_status=0):
        source = ROOT.joinpath("Jenkinsfile").read_text(encoding="utf-8")
        wrapper = source.split("def linuxUploadRun(", 1)[1].split("def uploadArtifact(", 1)[0]
        script = re.search(r"sh '''(.*?)'''", wrapper, re.S).group(1)
        env = os.environ.copy()
        env.pop("CI_ACTION", None)
        env.pop("CI_PLATFORM", None)
        env.update(WORKSPACE="/workspace/Flutter CI", CI_ROOT="/workspace/Flutter CI/ci-platform",
                   FLUTTER_IMAGE="flutter-ci:1.0", MSYS_NO_PATHCONV="1",
                   FIREBASE_CREDENTIALS_FILE="/workspace/Flutter CI@tmp/secretFiles/firebase.json",
                   GOOGLE_PLAY_CREDENTIALS_FILE="/workspace/Flutter CI@tmp/secretFiles/google.json",
                   UPLOAD_RELEASE_NOTES="Release $(echo DO_NOT_EXECUTE) `echo DO_NOT_EXECUTE`")
        if action is not None:
            env["CI_ACTION"] = action
        if platform is not None:
            env["CI_PLATFORM"] = platform
        stub = 'docker() { printf "%s\\n" "$@"; return ' + str(docker_status) + '; }\n'
        return subprocess.run([SHELL, "-x", "-c", stub + script], env=env,
                              text=True, capture_output=True, timeout=10)

    def test_upload_and_validation_preserve_argument_boundaries(self):
        for action, platform in (("validate", None), ("validate", ""), ("upload", "android")):
            with self.subTest(action=action, platform=platform):
                result = self.run_wrapper(action, platform)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = result.stdout.splitlines()
                expected = ["python3", "/workspace/Flutter CI/ci-platform/scripts/upload.py", action]
                if platform:
                    expected += ["--project", "/workspace/Flutter CI/app", "--platform", platform]
                self.assertEqual(args[args.index("python3"):], expected)
                self.assertEqual(args[args.index("-w") + 1], "/workspace/Flutter CI/ci-platform")
                self.assertIn("BUNDLE_GEMFILE=/workspace/Flutter CI/ci-platform/scripts/upload/Gemfile", args)

    def test_upload_forwards_credentials_by_environment_name_without_tracing_values(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = result.stdout.splitlines()
        forwarded = [args[i + 1] for i, arg in enumerate(args[:-1]) if arg == "-e"]
        for name in ("FIREBASE_CREDENTIALS_FILE", "GOOGLE_PLAY_CREDENTIALS_FILE",
                     "UPLOAD_RELEASE_NOTES", "PLATFORM", "IOS_EXPORT_METHOD", "ANDROID_ARTIFACT_TYPE",
                     "ANDROID_UPLOAD_DESTINATION", "IOS_UPLOAD_DESTINATION", "WEB_UPLOAD_DESTINATION"):
            self.assertIn(name, forwarded)
        self.assertNotIn("secretFiles", result.stdout + result.stderr)
        self.assertNotIn("DO_NOT_EXECUTE", result.stdout + result.stderr)
        self.assertNotIn("docker run", result.stderr)
        self.assertNotIn("ANDROID_KEYSTORE_FILE", forwarded)
        self.assertNotIn("ANDROID_STORE_PASSWORD", forwarded)

    def test_upload_propagates_docker_failure_and_requires_action(self):
        self.assertEqual(self.run_wrapper(docker_status=42).returncode, 42)
        result = self.run_wrapper(action=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CI_ACTION", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
