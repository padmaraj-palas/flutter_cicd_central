#!/usr/bin/env python3
"""Portable iOS contracts. Build commands are stubbed; these do not replace Xcode validation."""
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ios_build", REPO / "scripts/build-ios.py")
ios = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ios)

class IOSBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "pubspec.yaml").write_text("name: fixture\n")
        (self.root / "ios/Runner.xcodeproj").mkdir(parents=True)
        self.settings = {"ENVIRONMENT": "testing", "APP_NAME": "Contract App", "API_BASE_URL": "https://api.acme.test",
                         "IOS_BUNDLE_ID": "com.acme.contract"}
        self.signing = {"team_id": "ABCDE12345", "export_method": "release-testing", "signing_style": "manual",
                        "provisioning_profile": "Contract Profile", "code_sign_identity": "Apple Distribution", "release_signing": "existing-keychain"}
        self.commands = []
        self.export = True
        self.wrong_id = False
        self.addCleanup(self.temp.cleanup)

    def app(self, destination, simulator):
        destination.mkdir(parents=True, exist_ok=True)
        info = {"CFBundleIdentifier": "com.wrong.app" if self.wrong_id else self.settings["IOS_BUNDLE_ID"],
                "CFBundleDisplayName": self.settings["APP_NAME"], "CFBundleExecutable": "Runner",
                "CFBundleSupportedPlatforms": ["iPhoneSimulator" if simulator else "iPhoneOS"]}
        (destination / "Info.plist").write_bytes(plistlib.dumps(info))
        (destination / "Runner").write_bytes(b"fake test executable")

    def fake_run(self, args, **kwargs):
        args = [str(a) for a in args]
        self.commands.append(args)
        if args[:3] == ["flutter", "build", "ios"]:
            self.app(self.root / "build/ios/iphonesimulator/Runner.app", True)
        if args[:3] == ["flutter", "build", "ipa"] and self.export:
            app = self.root / "fixture/Payload/Runner.app"
            self.app(app, False)
            output = self.root / "build/ios/ipa"
            output.mkdir(parents=True)
            with zipfile.ZipFile(output / "result.ipa", "w") as archive:
                for p in app.iterdir():
                    archive.write(p, "Payload/Runner.app/" + p.name)
        if args[:3] == ["ditto", "-x", "-k"]:
            with zipfile.ZipFile(args[3]) as archive:
                archive.extractall(args[4])
        elif args[:3] == ["ditto", "-c", "-k"]:
            Path(args[-1]).write_bytes(b"simulator zip fixture")

    def build(self, environment, mode):
        with patch.object(ios.sys, "platform", "darwin"), \
             patch.object(ios, "settings", return_value=(self.settings, self.signing)), \
             patch.object(ios, "run", side_effect=self.fake_run), patch.dict(os.environ, {"BUILD_MODE": mode}, clear=True):
            ios.build(self.root)

    def test_six_combinations_and_defines(self):
        for environment in ("testing", "staging", "production"):
            for mode in ("debug", "release"):
                with self.subTest(environment=environment, mode=mode):
                    self.settings["ENVIRONMENT"] = environment
                    self.build(environment, mode)
                    ext = "zip" if mode == "debug" else "ipa"
                    self.assertTrue((self.root / f"build/ci/{environment}/{mode}/ios/app.{ext}").is_file())
                    marker = self.root / f"build/ci/{environment}/{mode}/ios/SUCCESS"
                    self.assertEqual(marker.read_text(), f"{environment} {mode} ios\n")
                    command = next(c for c in reversed(self.commands) if c[:2] == ["flutter", "build"])
                    self.assertIn(f"--dart-define=ENVIRONMENT={environment}", command)
                    self.assertNotIn("--flavor", command)

    def test_existing_scheme_passed_to_flutter(self):
        with patch.object(ios.sys, "platform", "darwin"), patch.object(ios, "settings", return_value=(self.settings, self.signing)), patch.object(ios, "run", side_effect=self.fake_run), patch.dict(os.environ, {"BUILD_MODE": "debug", "IOS_SCHEME": "preview"}, clear=True):
            ios.build(self.root)
        command = next(c for c in self.commands if c[:2] == ["flutter", "build"])
        self.assertEqual(command[command.index("--flavor") + 1], "preview")

    def test_release_signing_parameters_are_required(self):
        base = {"ENVIRONMENT": "preview", "APP_NAME": "Preview App", "IOS_BUNDLE_ID": "com.example.123preview", "IOS_RELEASE_SIGNING": "existing-keychain", "IOS_TEAM_ID": "ABCDE12345", "IOS_EXPORT_METHOD": "release-testing", "IOS_SIGNING_STYLE": "manual", "IOS_PROFILE_NAME": "Preview", "IOS_CODE_SIGN_IDENTITY": "Apple Distribution"}
        with patch.dict(os.environ, base, clear=True):
            values, signing = ios.settings(True)
            self.assertEqual(signing["provisioning_profile"], "Preview")
            self.assertEqual(values["IOS_BUNDLE_ID"], "com.example.123preview")
        for key in ("IOS_TEAM_ID", "IOS_EXPORT_METHOD", "IOS_SIGNING_STYLE", "IOS_PROFILE_NAME", "IOS_CODE_SIGN_IDENTITY"):
            with self.subTest(key=key), patch.dict(os.environ, {**base, key: ""}, clear=True):
                with self.assertRaises(ValueError):
                    ios.settings(True)

    def test_stale_ipa_cannot_hide_export_failure(self):
        output = self.root / "build/ios/ipa"
        output.mkdir(parents=True)
        (output / "old.ipa").write_bytes(b"stale")
        self.export = False
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.build("testing", "release")
        self.assertFalse((self.root / "build/ci/testing/release/ios/app.ipa").exists())

    def test_wrong_identity_fails(self):
        self.wrong_id = True
        with self.assertRaisesRegex(ValueError, "bundle ID/display name"):
            self.build("testing", "debug")

    def test_non_mac_rejected(self):
        with patch.object(ios.sys, "platform", "linux"):
            with self.assertRaisesRegex(ValueError, "native macOS"):
                with patch.dict(os.environ, {"BUILD_MODE": "debug"}, clear=True):
                    ios.build(self.root)

    def test_missing_jenkins_bindings_fail(self):
        self.signing["release_signing"] = "jenkins"
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "all three credential bindings"):
                with ios.signing_session(self.signing, self.settings["IOS_BUNDLE_ID"]):
                    self.fail("Missing signing credentials accepted")

    def test_security_errors_redacted(self):
        result = subprocess.CompletedProcess([], 1, stdout=b"secret", stderr=b"password")
        with patch.object(ios.subprocess, "run", return_value=result):
            with self.assertRaises(ValueError) as error:
                ios.quiet(["security", "import", "private-secret"])
            self.assertNotIn("private-secret", str(error.exception))
            self.assertNotIn("password", str(error.exception))


    @unittest.skipIf(os.name == "nt", "keychain lock uses POSIX fcntl")
    def test_temporary_signing_cleanup_after_build_failure(self):
        profile = self.root / "input.mobileprovision"
        profile.write_bytes(b"profile fixture")
        keychains = []
        commands = []
        def security(args, **kwargs):
            args = [str(x) for x in args]
            commands.append(args)
            if args[1] == "cms":
                return plistlib.dumps({"TeamIdentifier": ["ABCDE12345"], "Name": "Contract Profile",
                    "UUID": "ABCD-1234", "Entitlements": {"application-identifier": "ABCDE12345.com.acme.contract"}})
            if args[1] == "list-keychains" and "-s" not in args:
                return b'"/old.keychain"'
            if args[1] == "create-keychain":
                Path(args[-1]).touch()
                keychains.append(Path(args[-1]))
            if args[1] == "delete-keychain":
                Path(args[-1]).unlink()
            return b""
        self.signing["release_signing"] = "jenkins"
        bindings = {"IOS_P12_FILE": str(self.root / "certificate.p12"), "IOS_P12_PASSWORD": "test-fixture",
                    "IOS_PROFILE_FILE": str(profile)}
        with patch.object(ios.Path, "home", return_value=self.root), patch.object(ios, "quiet", side_effect=security), patch.dict(os.environ, bindings, clear=True):
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                with ios.signing_session(self.signing, self.settings["IOS_BUNDLE_ID"]):
                    raise RuntimeError("build failed")
        self.assertTrue(keychains)
        self.assertFalse(any(p.exists() for p in keychains))
        self.assertFalse(list((self.root / "Library").rglob("*.mobileprovision")))
        restored = [c for c in commands if c[1] == "list-keychains" and "-s" in c][-1]
        self.assertEqual(restored[-1], "/old.keychain")
        self.assertEqual(len(restored), 6)

    def test_settings_come_only_from_jenkins_environment(self):
        env = {"ENVIRONMENT": "preview", "APP_NAME": "Preview App", "IOS_BUNDLE_ID": "com.example.preview"}
        with patch.dict(os.environ, env, clear=True):
            values, signing = ios.settings(False)
            self.assertEqual(values, env)
            with self.assertRaisesRegex(ValueError, "IOS_RELEASE_SIGNING"):
                ios.settings(True)

    def test_invalid_identity_and_environment_rejected(self):
        base = {"ENVIRONMENT": "preview", "APP_NAME": "Preview App", "IOS_BUNDLE_ID": "com.example.preview"}
        for key, value in (("ENVIRONMENT", "../outside"), ("APP_NAME", "$(SECRET)"), ("IOS_BUNDLE_ID", "com.*")):
            with self.subTest(key=key), patch.dict(os.environ, {**base, key: value}, clear=True):
                with self.assertRaises(ValueError):
                    ios.settings(False)

    def test_credentials_removed_from_app_commands(self):
        bindings = {"BUILD_MODE": "debug", "IOS_P12_PASSWORD": "secret", "IOS_P12_FILE": "secret.p12", "IOS_PROFILE_FILE": "profile"}
        calls = []
        def run(args, **kwargs):
            calls.append(([str(a) for a in args], kwargs))
            return self.fake_run(args, **kwargs)
        with patch.object(ios.sys, "platform", "darwin"), patch.object(ios, "settings", return_value=(self.settings, self.signing)), patch.object(ios, "run", side_effect=run), patch.dict(os.environ, bindings, clear=True):
            ios.build(self.root)
        for args, kwargs in calls:
            if args[0] in ("bundle", "flutter"):
                self.assertFalse(set(bindings).intersection(kwargs["env"]) - {"BUILD_MODE"})

if __name__ == "__main__":
    unittest.main()
