"""Portable contract tests; Flutter/native tool execution is stubbed explicitly."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("central_build", Path(__file__).resolve().parents[1] / "scripts/build.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
PARAMS = dict(ENVIRONMENT="staging", BUILD_MODE="debug", APP_NAME="Central Staging", API_BASE_URL="https://staging.example.test/v1?a=b&c=d", ANDROID_APPLICATION_ID="com.example.central.staging", IOS_BUNDLE_ID="com.example.central.staging")


def encode_varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def field(number, value):
    value = value.encode() if isinstance(value, str) else value
    return encode_varint(number * 8 + 2) + encode_varint(len(value)) + value


def xml_node(name, attributes=(), children=()):
    element = field(3, name)
    for namespace, key, value in attributes:
        element += field(4, field(1, namespace) + field(2, key) + field(3, value))
    for child in children:
        element += field(5, child)
    return field(1, element)


def bundle(path, package, label):
    application = xml_node("application", [(runner.ANDROID_NS, "label", label)])
    manifest = xml_node("manifest", [("", "package", package)], [application])
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("base/manifest/AndroidManifest.xml", manifest)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = (Path(self.temporary.name) / "app").resolve()
        self.project.mkdir()
        (self.project / "pubspec.yaml").write_text("name: untouched_app\n")
        (self.project / "lib").mkdir()
        (self.project / "lib/main.dart").write_text("void main() {}\n")
        self.env = patch.dict(os.environ, PARAMS)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.values = runner.settings(PARAMS)

    def web(self):
        web = self.project / "web"
        web.mkdir()
        (web / "index.html").write_text('<html><head><title>Original</title><meta name="apple-mobile-web-app-title" content="Original"></head></html>')
        (web / "manifest.json").write_text(json.dumps(dict(name="Original", short_name="Original", icons=[{"src": "icon.png"}])))

    def android(self, kotlin=False):
        directory = self.project / "android/app"
        directory.mkdir(parents=True)
        script = directory / ("build.gradle.kts" if kotlin else "build.gradle")
        script.write_text("// existing project configuration\n")
        for source in ("main", "staging"):
            manifest = directory / f"src/{source}/AndroidManifest.xml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application android:label="Old" android:name="${applicationName}"><activity android:name=".MainActivity" android:label="Old launcher"><intent-filter><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity></application></manifest>')
        return script

    def test_requires_public_parameters_and_rejects_expressions(self):
        for key in PARAMS:
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.settings({k: v for k, v in PARAMS.items() if k != key})
        for key, value in [("APP_NAME", "$(whoami)"), ("API_BASE_URL", "https://user:password@example.test"), ("API_BASE_URL", "https://host/$(id)"), ("ANDROID_APPLICATION_ID", "bad-id"), ("IOS_BUNDLE_ID", "com.bad_id"), ("ANDROID_FLAVOR", "../../escape"), ("IOS_SCHEME", "")]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                runner.settings(dict(PARAMS, **{key: value}))

    def test_native_patch_preserves_placeholders_and_supports_both_gradle_formats(self):
        for kotlin in (False, True):
            with self.subTest(kotlin=kotlin):
                if (self.project / "android").exists():
                    import shutil
                    shutil.rmtree(self.project / "android")
                script = self.android(kotlin)
                runner.prepare_android(self.project, PARAMS["APP_NAME"])
                self.assertIn("scripts/android/override.gradle", script.read_text())
                self.assertIn("apply(from" if kotlin else "apply from:", script.read_text())
                for manifest in (self.project / "android/app/src").glob("*/AndroidManifest.xml"):
                    app = ET.parse(manifest).getroot().find("application")
                    self.assertEqual(app.get("{" + runner.ANDROID_NS + "}label"), PARAMS["APP_NAME"])
                    self.assertEqual(app.get("{" + runner.ANDROID_NS + "}name"), "${applicationName}")
                    self.assertEqual(app.find("activity").get("{" + runner.ANDROID_NS + "}label"), PARAMS["APP_NAME"])
                with self.assertRaises(ValueError):
                    runner.prepare_android(self.project, PARAMS["APP_NAME"])

    def test_web_build_packages_parameter_name_and_literal_argv_without_ci_files(self):
        self.web()
        calls = []
        def fake_run(args, project, **kwargs):
            calls.append(args)
            if args[:3] == ["flutter", "build", "web"]:
                import shutil
                target = project / "build/web"
                shutil.copytree(project / "web", target)
                (target / "main.dart.js").write_text("compiled fixture")
            return subprocess.CompletedProcess(args, 0)
        with patch.object(runner, "run", side_effect=fake_run):
            runner.build(self.project, "web", self.values)
        artifact = self.project / "build/ci/staging/debug/web/app.zip"
        with zipfile.ZipFile(artifact) as archive:
            self.assertEqual(json.loads(archive.read("manifest.json"))["name"], PARAMS["APP_NAME"])
            self.assertIn(PARAMS["APP_NAME"], archive.read("index.html").decode())
        self.assertIn("--dart-define=API_BASE_URL=" + PARAMS["API_BASE_URL"], calls[-1])
        self.assertEqual((artifact.parent / "SUCCESS").read_text(), "staging debug web\n")
        self.assertFalse((self.project / "ci").exists())
        self.assertFalse((self.project / "Jenkinsfile").exists())
        self.assertEqual((self.project / "lib/main.dart").read_text(), "void main() {}\n")

    def test_stale_web_artifact_cannot_satisfy_noop_build(self):
        self.web()
        output = self.project / "build/ci/staging/debug/web"
        output.mkdir(parents=True)
        (output / "SUCCESS").write_text("old")
        stale = self.project / "build/web"
        stale.mkdir()
        (stale / "main.dart.js").write_text("old")
        with patch.object(runner, "run"), self.assertRaises(ValueError):
            runner.build(self.project, "web", self.values)
        self.assertFalse((output / "SUCCESS").exists())
        self.assertFalse(stale.exists())

    def test_aab_manifest_exact_identity_and_label_verification(self):
        artifact = self.project / "bundle.aab"
        bundle(artifact, PARAMS["ANDROID_APPLICATION_ID"], PARAMS["APP_NAME"])
        runner.verify_android(artifact, self.values, self.project)
        for package, label in [(PARAMS["ANDROID_APPLICATION_ID"] + ".suffix", PARAMS["APP_NAME"]), (PARAMS["ANDROID_APPLICATION_ID"], "Other")]:
            bundle(artifact, package, label)
            with self.assertRaises(ValueError):
                runner.verify_android(artifact, self.values, self.project)
        with self.assertRaises(ValueError):
            runner.proto_fields(b"\x0a\xff")

    def test_apk_verifier_checks_application_and_launcher_identity(self):
        sdk = self.project / "sdk"
        aapt = sdk / "build-tools/36.0.0/aapt"
        aapt.parent.mkdir(parents=True)
        aapt.write_text("tool fixture")
        artifact = self.project / "app.apk"
        artifact.write_bytes(b"fixture")
        good = f"package: name='{PARAMS['ANDROID_APPLICATION_ID']}' versionCode='1'\napplication-label:'{PARAMS['APP_NAME']}'\nlaunchable-activity: name='com.original.MainActivity' label='{PARAMS['APP_NAME']}' icon=''\n"
        with patch.dict(os.environ, {"ANDROID_SDK_ROOT": str(sdk)}):
            with patch.object(runner, "run", return_value=subprocess.CompletedProcess([], 0, stdout=good)):
                runner.verify_android(artifact, self.values, self.project)
            for bad in (good.replace(PARAMS["ANDROID_APPLICATION_ID"], "com.wrong.app"), good.replace("application-label:'Central Staging'", "application-label:'Wrong'"), good.replace("label='Central Staging'", "label='Wrong launcher'")):
                with patch.object(runner, "run", return_value=subprocess.CompletedProcess([], 0, stdout=bad)), self.assertRaises(ValueError):
                    runner.verify_android(artifact, self.values, self.project)

    def test_android_release_uses_existing_flavor_and_verifies_new_bundle(self):
        self.android()
        values = dict(self.values, BUILD_MODE="release", ANDROID_FLAVOR="staging")
        calls = []
        def fake_run(args, project, **kwargs):
            calls.append(args)
            if args[:3] == ["flutter", "build", "appbundle"]:
                bundle(project / "build/app/outputs/bundle/stagingRelease/app-staging-release.aab", values["ANDROID_APPLICATION_ID"], values["APP_NAME"])
            return subprocess.CompletedProcess(args, 0)
        with patch.dict(os.environ, {"ANDROID_RELEASE_SIGNING": "project"}), patch.object(runner, "run", side_effect=fake_run):
            runner.build(self.project, "android", values)
        self.assertIn("--release", calls[-1])
        self.assertEqual(calls[-1][calls[-1].index("--flavor") + 1], "staging")
        self.assertTrue((self.project / "build/ci/staging/release/android/app.aab").is_file())
        self.assertFalse((self.project / "ci").exists())

    def test_release_requires_explicit_signing_and_all_bindings_before_edits(self):
        values = dict(self.values, BUILD_MODE="release")
        with self.assertRaises(ValueError):
            runner.validate_android_signing(values, {})
        runner.validate_android_signing(values, {"ANDROID_RELEASE_SIGNING": "project"})
        for values_env in ({"ANDROID_RELEASE_SIGNING": "jenkins"}, {"ANDROID_RELEASE_SIGNING": "unsupported"}):
            with self.assertRaises(ValueError):
                runner.validate_android_signing(values, values_env)
        keystore = self.project / "signing.jks"
        keystore.write_bytes(b"fixture")
        bindings = dict(ANDROID_RELEASE_SIGNING="jenkins", ANDROID_KEYSTORE_FILE=str(keystore), ANDROID_STORE_PASSWORD="secret", ANDROID_KEY_ALIAS="upload", ANDROID_KEY_PASSWORD="secret")
        runner.validate_android_signing(values, bindings)
        for key in ("ANDROID_KEYSTORE_FILE", "ANDROID_STORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.validate_android_signing(values, {k: v for k, v in bindings.items() if k != key})

    def test_quality_runs_from_unmodified_app_and_failure_propagates(self):
        (self.project / "test").mkdir()
        with patch.object(runner, "run") as command:
            runner.quality(self.project)
        self.assertEqual([call.args[0][:2] for call in command.call_args_list], [["flutter", "pub"], ["dart", "format"], ["flutter", "analyze"], ["flutter", "test"]])
        with patch.object(runner, "run", side_effect=subprocess.CalledProcessError(1, ["flutter", "analyze"])), self.assertRaises(subprocess.CalledProcessError):
            runner.quality(self.project)

    def test_pubget_does_not_receive_signing_credentials(self):
        self.web()
        captured = []
        def stop_after_pubget(args, project, **kwargs):
            captured.append(kwargs["env"])
            raise ValueError("stop before build")
        secret_env = dict(IOS_P12_PASSWORD="private-ios", ANDROID_STORE_PASSWORD="private-android", ANDROID_KEYSTORE_FILE="private-file")
        with patch.dict(os.environ, secret_env), patch.object(runner, "run", side_effect=stop_after_pubget), self.assertRaises(ValueError):
            runner.build(self.project, "web", self.values)
        self.assertEqual(captured[0]["APP_NAME"], PARAMS["APP_NAME"])
        for key in secret_env:
            self.assertNotIn(key, captured[0])

    def test_paths_cannot_target_central_or_escape_project(self):
        with self.assertRaises(ValueError):
            runner.project_path(str(runner.CENTRAL))
        with self.assertRaises(ValueError):
            runner.project_path("relative/app")
        with self.assertRaises(ValueError):
            runner.inside(self.project, "../outside")
        self.assertEqual(runner.project_path(str(self.project)), self.project.resolve())


if __name__ == "__main__":
    unittest.main()
