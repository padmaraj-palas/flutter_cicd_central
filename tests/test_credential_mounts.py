"""Execute Jenkins shell wrappers with fixture credentials; no real service secrets."""
import csv
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHELL = shutil.which("sh")
if not SHELL and os.name == "nt":
    candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    if candidate.is_file():
        SHELL = str(candidate)


def shell_path(path):
    value = path.resolve().as_posix()
    if os.name == "nt":
        value = "/" + value[0].lower() + value[2:]
    return value


def wrapper(name):
    source = (ROOT / "Jenkinsfile").read_text(encoding="utf-8")
    section = source.split("def " + name + "(", 1)[1].split("\ndef ", 1)[0]
    return re.search(r"sh '''(.*?)'''", section, re.S).group(1)


@unittest.skipUnless(SHELL, "A POSIX shell is required")
class CredentialMountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ci-credential-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "Flutter CI"
        self.workspace.mkdir()
        self.credentials = self.root / "Flutter CI@tmp/secretFiles"
        self.credentials.mkdir(parents=True)
        self.files = {}
        for key, name in (("ANDROID_KEYSTORE_FILE", "release, key.jks"),
                          ("FIREBASE_CREDENTIALS_FILE", "firebase, service.json"),
                          ("GOOGLE_PLAY_CREDENTIALS_FILE", "google, service.json")):
            path = self.credentials / name
            path.write_text("DUMMY TEST CREDENTIAL", encoding="utf-8")
            self.files[key] = path
        self.env = dict(os.environ, MSYS_NO_PATHCONV="1", WORKSPACE=shell_path(self.workspace),
                        CI_ROOT=shell_path(self.workspace / "ci-platform"), FLUTTER_IMAGE="flutter-ci:1.0",
                        CI_ACTION="build", CI_PLATFORM="android", BUILD_MODE="release",
                        ANDROID_RELEASE_SIGNING="jenkins", ANDROID_UPLOAD_DESTINATION="firebase")
        self.env.update({key: shell_path(path) for key, path in self.files.items()})

    def run_wrapper(self, name="linuxRun", containerized=False, status=0, **overrides):
        env = dict(self.env, **overrides)
        stub = ("docker() { if [ \"$1\" = container ]; then return " +
                ("0" if containerized else "1") +
                "; fi; printf '%s\\0' \"$@\"; return " + str(status) + "; }\n")
        result = subprocess.run([SHELL, "-x", "-c", stub + wrapper(name)], env=env,
                                capture_output=True, text=True, timeout=10)
        args = result.stdout.rstrip("\0").split("\0") if result.stdout else []
        return result, args

    def mounts(self, args):
        return [next(csv.reader([args[i + 1]])) for i, arg in enumerate(args[:-1]) if arg == "--mount"]

    def test_host_mounts_only_selected_file_readonly(self):
        cases = [("linuxRun", "build", "firebase", "ANDROID_KEYSTORE_FILE"),
                 ("linuxUploadRun", "upload", "firebase", "FIREBASE_CREDENTIALS_FILE"),
                 ("linuxUploadRun", "upload", "google", "GOOGLE_PLAY_CREDENTIALS_FILE")]
        for name, action, destination, selected in cases:
            with self.subTest(selected=selected):
                result, args = self.run_wrapper(name, CI_ACTION=action, ANDROID_UPLOAD_DESTINATION=destination)
                self.assertEqual(result.returncode, 0, result.stderr)
                path = self.env[selected]
                self.assertEqual(self.mounts(args), [["type=bind", "source=" + path, "target=" + path, "readonly"]])
                self.assertIn(self.env["WORKSPACE"] + ":" + self.env["WORKSPACE"], args)
                self.assertNotIn("--volumes-from", args)
                self.assertNotIn("secretFiles", result.stderr)
                self.assertNotIn("DUMMY TEST CREDENTIAL", result.stdout + result.stderr)
                for other in self.files:
                    if other != selected:
                        self.assertNotIn(self.env[other], result.stdout)

    def test_containerized_keeps_inherited_volume_without_host_source_checks(self):
        for name, action in (("linuxRun", "build"), ("linuxUploadRun", "upload")):
            with self.subTest(name=name):
                result, args = self.run_wrapper(name, containerized=True, CI_ACTION=action,
                                               ANDROID_KEYSTORE_FILE="/not/on/docker/host/key.jks",
                                               FIREBASE_CREDENTIALS_FILE="/not/on/docker/host/firebase.json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--volumes-from", args)
                self.assertEqual(args[args.index("--volumes-from") + 1], "jenkins")
                self.assertEqual(self.mounts(args), [])
                self.assertNotIn(self.env["WORKSPACE"] + ":" + self.env["WORKSPACE"], args)

    def test_noncredential_steps_do_not_mount_ambient_secrets(self):
        cases = [("linuxRun", dict(CI_ACTION="validate")),
                 ("linuxRun", dict(CI_ACTION="quality")),
                 ("linuxRun", dict(BUILD_MODE="debug")),
                 ("linuxRun", dict(CI_PLATFORM="web")),
                 ("linuxRun", dict(ANDROID_RELEASE_SIGNING="project")),
                 ("linuxUploadRun", dict(CI_ACTION="validate")),
                 ("linuxUploadRun", dict(CI_ACTION="upload", ANDROID_UPLOAD_DESTINATION="none")),
                 ("uploadArtifact", {})]
        for name, changes in cases:
            with self.subTest(name=name, changes=changes):
                result, args = self.run_wrapper(name, **changes)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.mounts(args), [])
                if name == "uploadArtifact":
                    self.assertEqual(args[args.index("-w") + 1], self.env["CI_ROOT"] + "/scripts/upload")
                    self.assertIn("BUNDLE_GEMFILE=" + self.env["CI_ROOT"] + "/scripts/upload/Gemfile", args)
                    self.assertTrue((ROOT / "scripts/upload/Gemfile").is_file())

    def test_missing_relative_or_directory_credentials_fail_before_docker_run(self):
        for name, action, key in (("linuxRun", "build", "ANDROID_KEYSTORE_FILE"),
                                  ("linuxUploadRun", "upload", "FIREBASE_CREDENTIALS_FILE")):
            for bad in ("", "relative.json", shell_path(self.root / "missing"), shell_path(self.credentials)):
                with self.subTest(name=name, value=bad):
                    result, args = self.run_wrapper(name, CI_ACTION=action, **{key: bad})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(args, [])

    def test_docker_failure_propagates_in_both_topologies(self):
        for name, action in (("linuxRun", "build"), ("linuxUploadRun", "upload")):
            for containerized in (False, True):
                with self.subTest(name=name, containerized=containerized):
                    result, _ = self.run_wrapper(name, containerized=containerized, status=42, CI_ACTION=action)
                    self.assertEqual(result.returncode, 42)

    @unittest.skipIf(os.name == "nt", "Windows filenames cannot contain double quotes")
    def test_quote_in_credential_filename_uses_valid_mount_csv(self):
        path = self.credentials / 'key,"quoted".jks'
        path.write_text("DUMMY", encoding="utf-8")
        result, args = self.run_wrapper(ANDROID_KEYSTORE_FILE=str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.mounts(args), [["type=bind", "source=" + str(path), "target=" + str(path), "readonly"]])


if __name__ == "__main__":
    unittest.main()
