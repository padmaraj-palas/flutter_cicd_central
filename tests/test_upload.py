import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import upload
from upload_settings import DEFAULTS, validate


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.env = dict(DEFAULTS, PLATFORM="android", ENVIRONMENT="staging", BUILD_MODE="release", ANDROID_APPLICATION_ID="com.example.app", IOS_BUNDLE_ID="com.example.app", IOS_EXPORT_METHOD="app-store-connect", PATH=os.environ["PATH"])
        self.key = self.root / "key.json"
        self.key.write_text(json.dumps(dict(type="service_account", project_id="project", client_email="ci@example.com", private_key="PRIVATE SECRET")))
        self.env.update(FIREBASE_CREDENTIALS_FILE=str(self.key), GOOGLE_PLAY_CREDENTIALS_FILE=str(self.key), FIREBASE_CREDENTIALS_ID="firebase", GOOGLE_PLAY_CREDENTIALS_ID="google", FIREBASE_ANDROID_APP_ID="1:123:android:abc", FIREBASE_IOS_APP_ID="1:123:ios:abc")

    def artifact(self, platform="android", mode="release"):
        folder = self.root / "build/ci/staging" / mode / platform
        folder.mkdir(parents=True)
        (folder / "SUCCESS").write_text(f"staging {mode} {platform}\n")
        path = folder / ("app.ipa" if platform == "ios" else "app.aab" if mode == "release" else "app.apk")
        path.write_bytes(b"artifact")
        return path

    def test_old_jobs_default_none(self):
        self.assertEqual(validate({"PLATFORM": "web"})["ANDROID_UPLOAD_DESTINATION"], "none")

    def test_none_does_not_touch_files_or_run(self):
        with patch.object(upload.subprocess, "run") as run:
            upload.upload("missing", "android", self.env)
            run.assert_not_called()

    def test_firebase_command_scopes_secrets_and_cwd(self):
        self.env.update(ANDROID_UPLOAD_DESTINATION="firebase", FIREBASE_GROUPS="qa,staff", UPLOAD_RELEASE_NOTES="New build", IOS_P12_PASSWORD="SIGN SECRET", FIREBASE_TOKEN="TOKEN", GOOGLE_APPLICATION_CREDENTIALS="ambient.json", RUBYOPT="-revil", NODE_OPTIONS="--require evil.js")
        artifact = self.artifact()
        def check(command, **kwargs):
            self.assertEqual(command, ["bundle", "exec", "ruby", str(upload.CENTRAL / "scripts/upload/run.rb")])
            child = kwargs["env"]
            self.assertEqual(child["CI_UPLOAD_DESTINATION"], "firebase")
            self.assertEqual(child["CI_UPLOAD_PLATFORM"], "android")
            self.assertEqual(child["CI_UPLOAD_ARTIFACT"], str(artifact))
            self.assertEqual(child["BUNDLE_GEMFILE"], str(upload.CENTRAL / "scripts/upload/Gemfile"))
            self.assertEqual(child["BUNDLE_FROZEN"], "true")
            self.assertEqual(child["FIREBASE_GROUPS"], "qa,staff")
            self.assertEqual(child["UPLOAD_RELEASE_NOTES"], "New build")
            self.assertEqual(child["FIREBASE_CREDENTIALS_FILE"], str(self.key))
            for secret in ("IOS_P12_PASSWORD", "FIREBASE_TOKEN", "GOOGLE_APPLICATION_CREDENTIALS", "RUBYOPT", "NODE_OPTIONS", "GOOGLE_PLAY_CREDENTIALS_FILE"):
                self.assertNotIn(secret, kwargs["env"])
            self.assertNotEqual(kwargs["cwd"], self.root)
            self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        with patch.object(upload.subprocess, "run", side_effect=check):
            upload.upload(str(self.root), "android", self.env)

    def test_firebase_artifact_matrix_and_empty_optional_fields(self):
        for platform, mode in (("android", "debug"), ("android", "release"), ("ios", "release")):
            with self.subTest(platform=platform, mode=mode):
                env = {**self.env, "PLATFORM": platform, "BUILD_MODE": mode,
                       f"{platform.upper()}_UPLOAD_DESTINATION": "firebase",
                       "IOS_EXPORT_METHOD": "release-testing", "BUNDLE_PATH": "/opt/upload-gems"}
                artifact = self.artifact(platform, mode)
                with patch.object(upload.subprocess, "run") as run:
                    upload.upload(str(self.root), platform, env)
                child = run.call_args.kwargs["env"]
                self.assertEqual(child["CI_UPLOAD_PLATFORM"], platform)
                self.assertEqual(child["CI_UPLOAD_ARTIFACT"], str(artifact))
                self.assertEqual(child[f"FIREBASE_{platform.upper()}_APP_ID"], env[f"FIREBASE_{platform.upper()}_APP_ID"])
                self.assertEqual(child["FIREBASE_GROUPS"], "")
                self.assertEqual(child["UPLOAD_RELEASE_NOTES"], "")
                self.assertEqual(child["BUNDLE_PATH"], "/opt/upload-gems")
                self.assertFalse(run.call_args.kwargs["cwd"].exists())

    def test_firebase_failure_is_sanitized(self):
        self.env["ANDROID_UPLOAD_DESTINATION"] = "firebase"
        self.artifact()
        for error, expected in ((FileNotFoundError(), "Upload tool is missing"),
                                (subprocess.CalledProcessError(7, ["PRIVATE SECRET"], stderr="PRIVATE SECRET"), "firebase upload failed ")):
            with self.subTest(error=type(error).__name__), patch.object(upload.subprocess, "run", side_effect=error):
                with self.assertRaises(ValueError) as caught:
                    upload.upload(str(self.root), "android", self.env)
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn("PRIVATE SECRET", str(caught.exception))

    def test_google_uses_central_ruby_and_metadata(self):
        self.env.update(ANDROID_UPLOAD_DESTINATION="google", UPLOAD_RELEASE_NOTES="New build", BUNDLE_PATH="/opt/gems")
        self.artifact()
        def check(command, **kwargs):
            self.assertEqual(command[:3], ["bundle", "exec", "ruby"])
            self.assertEqual(Path(command[3]), upload.CENTRAL / "scripts/upload/run.rb")
            self.assertEqual(kwargs["env"]["BUNDLE_PATH"], "/opt/gems")
            self.assertEqual(Path(kwargs["env"]["BUNDLE_GEMFILE"]), upload.CENTRAL / "scripts/upload/Gemfile")
            self.assertTrue(Path(command[3]).is_file())
            self.assertNotIn("GOOGLE_APPLICATION_CREDENTIALS", kwargs["env"])
            self.assertEqual((kwargs["cwd"] / "metadata/en-US/changelogs/default.txt").read_text(), "New build")
        with patch.object(upload.subprocess, "run", side_effect=check):
            upload.upload(str(self.root), "android", self.env)

    def test_appstore(self):
        self.env.update(PLATFORM="ios", IOS_UPLOAD_DESTINATION="appstore", APPSTORE_API_KEY_CREDENTIALS_ID="apple", APPSTORE_API_KEY_FILE=str(self.key))
        self.key.write_text(json.dumps(dict(key_id="id", issuer_id="issuer", key="PRIVATE SECRET")))
        self.artifact("ios")
        with patch.object(upload.subprocess, "run") as run:
            upload.upload(str(self.root), "ios", self.env)
            self.assertEqual(run.call_args.kwargs["env"]["APPSTORE_API_KEY_FILE"], str(self.key))
            self.assertNotIn("GOOGLE_PLAY_CREDENTIALS_FILE", run.call_args.kwargs["env"])

    def test_platform_and_export_restrictions(self):
        for changes in (dict(WEB_UPLOAD_DESTINATION="firebase"), dict(ANDROID_UPLOAD_DESTINATION="google", BUILD_MODE="debug"), dict(PLATFORM="ios", IOS_UPLOAD_DESTINATION="firebase", BUILD_MODE="debug"), dict(PLATFORM="ios", IOS_UPLOAD_DESTINATION="firebase"), dict(FIREBASE_GROUPS="qa --token=x"), dict(FIREBASE_CREDENTIALS_ID="{secret}"), dict(UPLOAD_RELEASE_NOTES="a\nb")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate({**self.env, **changes})

    def test_firebase_ios_allowed_exports(self):
        for method in ("release-testing", "debugging", "enterprise"):
            validate({**self.env, "PLATFORM": "ios", "IOS_UPLOAD_DESTINATION": "firebase", "IOS_EXPORT_METHOD": method})

    def test_missing_or_empty_artifact_and_wrong_marker(self):
        self.env["ANDROID_UPLOAD_DESTINATION"] = "google"
        with self.assertRaises(ValueError):
            upload.upload(str(self.root), "android", self.env)
        artifact = self.artifact()
        artifact.write_bytes(b"")
        with self.assertRaises(ValueError):
            upload.upload(str(self.root), "android", self.env)
        artifact.write_bytes(b"build")
        (artifact.parent / "SUCCESS").write_text("production release android\n")
        with self.assertRaises(ValueError):
            upload.upload(str(self.root), "android", self.env)

    def test_upload_errors_never_include_service_output(self):
        self.env["ANDROID_UPLOAD_DESTINATION"] = "google"
        self.artifact()
        error = subprocess.CalledProcessError(3, ["secret command"], output="PRIVATE SECRET", stderr="PRIVATE SECRET")
        with patch.object(upload.subprocess, "run", side_effect=error):
            with self.assertRaisesRegex(ValueError, "exit 3") as caught:
                upload.upload(str(self.root), "android", self.env)
            self.assertNotIn("PRIVATE SECRET", str(caught.exception))

    def test_bad_json_does_not_leak_contents(self):
        self.key.write_text("PRIVATE SECRET")
        with self.assertRaises(ValueError) as caught:
            upload.credential_file(self.env, "FIREBASE_CREDENTIALS_FILE")
        self.assertNotIn("PRIVATE SECRET", str(caught.exception))

    def test_traversal_environment(self):
        self.artifact()
        with self.assertRaises(ValueError):
            upload.artifact_path(str(self.root), {**self.env, "ENVIRONMENT": "../../.."}, "android")

if __name__ == "__main__":
    unittest.main()

