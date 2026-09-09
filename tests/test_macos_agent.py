#!/usr/bin/env python3
"""Mac agent ownership and secret handling, tested without Jenkins or macOS."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "automation/scripts"))
import macos_agent


class AgentClient:
    def __init__(self, config, owner=None):
        self.calls = []
        self.root = ET.Element("slave")
        values = {
            "description": owner or f"Managed by flutter-cicd-central; project_id={config['project_id']}",
            "remoteFS": "/Users/builder/jenkins-agent", "numExecutors": "1",
            "mode": "EXCLUSIVE", "label": config["parameters"]["MACOS_AGENT_LABEL"],
        }
        for name, value in values.items():
            ET.SubElement(self.root, name).text = value
        launcher = ET.SubElement(self.root, "launcher", {"class": "hudson.slaves.JNLPLauncher"})
        ET.SubElement(launcher, "webSocket").text = "true"

    def request(self, method, path, data=None, content_type=None):
        self.calls.append((method, path))
        if path.endswith("config.xml"):
            return 200, ET.tostring(self.root), {}
        return 200, b"<jnlp><application-desc><argument>abcdef0123456789</argument><argument>mac-builder</argument></application-desc></jnlp>", {}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((REPO / "automation/answers.example.json").read_text(encoding="utf-8-sig"))

    def test_owned_node_secret_saved_without_output_and_owner_only(self):
        client = AgentClient(self.config)
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "inbound-secret"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                macos_agent.ensure_agent(client, self.config, "mac-builder", "/Users/builder/jenkins-agent", secret)
            self.assertEqual(secret.read_text(), "abcdef0123456789\n")
            self.assertNotIn("abcdef0123456789", output.getvalue())
            self.assertEqual([call[0] for call in client.calls], ["GET", "GET"])
            if os.name != "nt":
                self.assertEqual(secret.stat().st_mode & 0o777, 0o600)

    def test_unrelated_node_is_not_modified_or_secret_requested(self):
        client = AgentClient(self.config, owner="Someone else's node")
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "inbound-secret"
            with self.assertRaises(ValueError):
                macos_agent.ensure_agent(client, self.config, "mac-builder", "/Users/builder/jenkins-agent", secret)
            self.assertFalse(secret.exists())
            self.assertEqual(len(client.calls), 1)

    def test_existing_secret_and_repository_destination_fail_before_network(self):
        client = AgentClient(self.config)
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "inbound-secret"
            secret.write_text("existing")
            with self.assertRaises(ValueError):
                macos_agent.ensure_agent(client, self.config, "mac-builder", "/Users/builder/jenkins-agent", secret)
            self.assertEqual(secret.read_text(), "existing")
        with self.assertRaises(ValueError):
            macos_agent.ensure_agent(client, self.config, "mac-builder", "/Users/builder/jenkins-agent",
                                     Path(__file__).resolve().parent / "forbidden-secret")
        self.assertEqual(client.calls, [])

    def test_invalid_remote_workspace_and_launcher_are_refused(self):
        client = AgentClient(self.config)
        with tempfile.TemporaryDirectory() as directory:
            for remote in ("/", "/Users", "relative", "/Users/builder/../other"):
                with self.assertRaises(ValueError):
                    macos_agent.ensure_agent(client, self.config, "mac-builder", remote, Path(directory) / "secret")
            self.assertEqual(client.calls, [])
            client.root.find("launcher/webSocket").text = "false"
            with self.assertRaises(ValueError):
                macos_agent.ensure_agent(client, self.config, "mac-builder", "/Users/builder/jenkins-agent",
                                         Path(directory) / "secret")
            self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
