#!/usr/bin/env python3
"""Portable contract tests; no Jenkins service or Flutter repository is changed."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
import setup


class FakeClient:
    def __init__(self, existing=None):
        self.existing = existing
        self.requests = []

    def request(self, method, path, data=None, content_type=None):
        self.requests.append((method, path, data, content_type))
        if method == "GET":
            if self.existing is None:
                raise urllib.error.HTTPError("http://localhost/job/test", 404, "Not Found", {}, None)
            return 200, self.existing, {}
        return 201, b"", {"Location": "http://localhost/jenkins/queue/item/42/"}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((Path(__file__).resolve().parents[1] / "answers.example.json").read_text(encoding="utf-8-sig"))
        self.data["confirmed"] = True

    def test_job_separates_central_scm_from_application_and_persists_one_choice(self):
        root = ET.fromstring(setup.job_xml(self.data))
        self.assertEqual(root.findtext(".//hudson.plugins.git.UserRemoteConfig/url"), self.data["ci"]["repository_url"])
        self.assertEqual(root.findtext(".//hudson.plugins.git.BranchSpec/name"), "refs/tags/v1.0.0")
        self.assertEqual(root.findtext("definition/scriptPath"), "Jenkinsfile")
        definitions = root.find("properties/hudson.model.ParametersDefinitionProperty/parameterDefinitions")
        params = {node.findtext("name"): node for node in definitions}
        self.assertEqual(set(params), set(setup.PARAMETERS))
        self.assertEqual(params["APP_REPOSITORY_URL"].findtext("defaultValue"),
                         self.data["parameters"]["APP_REPOSITORY_URL"])
        for name in setup.CHOICES:
            self.assertEqual([node.text for node in params[name].findall("choices/a/string")],
                             [self.data["parameters"][name]])
        self.assertEqual(root.findtext(".//hudson.triggers.SCMTrigger/spec"), "H/5 * * * *")
        self.assertNotIn("environment_file", ET.tostring(root, encoding="unicode"))

    def test_ci_commit_is_pinned_and_named_branch_tracks_branch(self):
        for selected in ("a" * 40, "b" * 64, "refs/tags/v1.0.0", "refs/heads/main"):
            changed = copy.deepcopy(self.data)
            changed["ci"]["ref"] = selected
            root = ET.fromstring(setup.job_xml(changed))
            self.assertEqual(root.findtext(".//hudson.plugins.git.BranchSpec/name"), selected)
        changed = copy.deepcopy(self.data)
        changed["ci"]["ref"] = "main"
        self.assertEqual(ET.fromstring(setup.job_xml(changed)).findtext(".//hudson.plugins.git.BranchSpec/name"), "*/main")

    def test_copied_job_can_select_independent_branch_and_identity(self):
        other = copy.deepcopy(self.data)
        other["job_name"] = "YourApp-Production-All"
        other["parameters"].update(ENVIRONMENT="production", PLATFORM="all", APP_BRANCH="main",
                                   APP_NAME="Your App", ANDROID_APPLICATION_ID="com.example.yourapp",
                                   IOS_BUNDLE_ID="com.example.yourapp")
        one = ET.fromstring(setup.job_xml(self.data))
        two = ET.fromstring(setup.job_xml(other))
        self.assertEqual(one.findtext(".//hudson.plugins.git.UserRemoteConfig/url"),
                         two.findtext(".//hudson.plugins.git.UserRemoteConfig/url"))
        values = {p.findtext("name"): p.findtext("defaultValue") or p.findtext("choices/a/string")
                  for p in two.find("properties/hudson.model.ParametersDefinitionProperty/parameterDefinitions")}
        self.assertEqual(values["ENVIRONMENT"], "production")
        self.assertEqual(values["APP_BRANCH"], "main")
        self.assertEqual(values["APP_NAME"], "Your App")

    def test_no_implicit_settings_and_no_secret_fields(self):
        for key in setup.PARAMETERS:
            with self.subTest(missing=key):
                changed = copy.deepcopy(self.data)
                del changed["parameters"][key]
                with self.assertRaises(ValueError):
                    setup.validate(changed)
        for changed in (
            {**self.data, "confirmed": False},
            {**self.data, "api_token": "do-not-store"},
            {**self.data, "parameters": {**self.data["parameters"], "IOS_P12_PASSWORD": "do-not-store"}},
        ):
            with self.assertRaises(ValueError):
                setup.validate(changed)

    def test_reject_unsafe_refs_and_urls(self):
        for key, value in (
            ("APP_BRANCH", "*/staging"), ("APP_BRANCH", "refs/tags/v1"),
            ("APP_BRANCH", "../other"), ("APP_BRANCH", "a/.bad/b"),
            ("APP_REPOSITORY_URL", "https://user:secret@example.com/app.git"),
            ("APP_REPOSITORY_URL", "https://example.com/app.git?token=secret"),
            ("APP_REPOSITORY_URL", "file:///tmp/app"),
            ("APP_REPOSITORY_URL", "ssh://example.com/app.git"),
            ("APP_REPOSITORY_URL", "https://example.com/my%20app.git"),
            ("APP_NAME", "name\nINJECTED=value"), ("FLUTTER_IMAGE", "flutter --privileged"),
            ("API_BASE_URL", "https://secret@example.com"),
        ):
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(self.data)
                changed["parameters"][key] = value
                with self.assertRaises(ValueError):
                    setup.validate(changed)
        for script in ("../Jenkinsfile", "/Jenkinsfile", "a/../Jenkinsfile"):
            changed = copy.deepcopy(self.data)
            changed["ci"]["script_path"] = script
            with self.assertRaises(ValueError):
                setup.validate(changed)

    def test_app_name_length_and_api_url_match_runtime_constraints(self):
        changed = copy.deepcopy(self.data)
        changed["parameters"]["APP_NAME"] = "A" * 80
        changed["parameters"]["API_BASE_URL"] = "https://api.example.com:8443/v1"
        setup.validate(changed)
        changed["parameters"]["APP_NAME"] = "A" * 81
        with self.assertRaises(ValueError):
            setup.validate(changed)
        for suffix in (":invalid/v1", ":65536/v1", "/v1$VALUE", "/v1" + chr(96),
                       "/v1\\\\unsafe", '/v1"quoted', "/v1'quoted", "/v1<unsafe", "/v1>unsafe"):
            changed = copy.deepcopy(self.data)
            changed["parameters"]["API_BASE_URL"] = "https://api.example.com" + suffix
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                setup.validate(changed)

    def test_explicit_polling_or_disabled_and_invalid_cron(self):
        for schedule in ("", "H/2 * * * *", "H(0-29)/5 * * * *", "@daily", "0 9 * * 1-5"):
            changed = copy.deepcopy(self.data)
            changed["jenkins"]["poll_schedule"] = schedule
            root = ET.fromstring(setup.job_xml(changed))
            self.assertEqual(root.findtext(".//hudson.triggers.SCMTrigger/spec"), schedule or None)
        for schedule in ("every minute", "60 * * * *", "*/0 * * * *", "* * * * *\n* * * * *", "0 9 * 13 *"):
            with self.assertRaises(ValueError):
                setup.cron(schedule)

    def test_android_release_requires_all_signing_credential_ids(self):
        p = self.data["parameters"]
        p.update(BUILD_MODE="release", ANDROID_RELEASE_SIGNING="jenkins")
        with self.assertRaises(ValueError):
            setup.validate(self.data)
        p.update(ANDROID_KEYSTORE_CREDENTIAL_ID="android-keystore",
                 ANDROID_STORE_PASSWORD_CREDENTIAL_ID="android-store-password",
                 ANDROID_KEY_ALIAS_CREDENTIAL_ID="android-key-alias",
                 ANDROID_KEY_PASSWORD_CREDENTIAL_ID="android-key-password")
        setup.validate(self.data)
        p["ANDROID_RELEASE_SIGNING"] = "project"
        with self.assertRaises(ValueError):
            setup.validate(self.data)

    def test_ios_release_requires_matching_signing_configuration(self):
        p = self.data["parameters"]
        p.update(PLATFORM="ios", BUILD_MODE="release")
        with self.assertRaises(ValueError):
            setup.validate(self.data)
        p.update(IOS_TEAM_ID="A1B2C3D4E5", IOS_PROFILE_NAME="Your App Staging Profile")
        setup.validate(self.data)
        p["IOS_RELEASE_SIGNING"] = "jenkins"
        with self.assertRaises(ValueError):
            setup.validate(self.data)
        p.update(IOS_P12_CREDENTIAL_ID="ios-p12", IOS_PASSWORD_CREDENTIAL_ID="ios-password",
                 IOS_PROFILE_CREDENTIAL_ID="ios-staging-profile")
        setup.validate(self.data)
        p["IOS_SIGNING_STYLE"] = "automatic"
        with self.assertRaises(ValueError):
            setup.validate(self.data)

    def test_ensure_creates_owned_updates_backup_every_revision_and_refuses_others(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            self.assertEqual(setup.ensure_job(client, self.data, directory)["action"], "created")
            self.assertTrue(client.requests[-1][1].startswith("createItem?name="))
            client = FakeClient(setup.job_xml(self.data))
            one = setup.ensure_job(client, self.data, directory)
            two = setup.ensure_job(client, self.data, directory)
            self.assertNotEqual(one["backup"], two["backup"])
            self.assertEqual(Path(one["backup"]).read_bytes(), setup.job_xml(self.data))
            unrelated = copy.deepcopy(self.data)
            unrelated["project_id"] = "unrelated"
            client = FakeClient(setup.job_xml(unrelated))
            with self.assertRaises(ValueError):
                setup.ensure_job(client, self.data, directory)
            self.assertEqual([r[0] for r in client.requests], ["GET"])

    def test_build_uses_current_saved_job_values_without_answers_overrides(self):
        current = copy.deepcopy(self.data)
        current["parameters"]["ENVIRONMENT"] = "production"
        client = FakeClient(setup.job_xml(current))
        result = setup.build_job(client, self.data)
        self.assertEqual(result["queue_id"], 42)
        self.assertEqual(client.requests[-1][2], b"")
        self.assertTrue(client.requests[-1][1].endswith("/buildWithParameters"))
        other = copy.deepcopy(self.data)
        other["project_id"] = "another-project"
        client = FakeClient(setup.job_xml(other))
        with self.assertRaises(ValueError):
            setup.build_job(client, self.data)
        self.assertEqual(len(client.requests), 1)

    def test_render_does_not_overwrite_and_duplicate_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "job.xml"
            setup.write_new(file, b"original")
            with self.assertRaises(FileExistsError):
                setup.write_new(file, b"replacement")
            self.assertEqual(file.read_bytes(), b"original")
            config = Path(directory) / "answers.json"
            config.write_text('{"confirmed":true,"confirmed":false}', encoding="utf-8")
            with self.assertRaises(ValueError):
                setup.read_config(config)


if __name__ == "__main__":
    unittest.main()
