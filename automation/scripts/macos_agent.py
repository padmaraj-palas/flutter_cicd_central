#!/usr/bin/env python3
"""Register one owned inbound Mac node and save its secret without displaying it."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET

from setup import Client, read_config


def secret_destination(secret_path, remote_fs):
    destination = Path(secret_path).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Use a new secret file; existing files and symlinks are never replaced.")
    resolved = destination.resolve()
    central = Path(__file__).resolve().parents[2]
    roots = [central]
    roots.extend(parent for parent in central.parents if (parent / ".git").exists())
    if os.name != "nt":
        roots.append(Path(remote_fs).resolve())
    if any(root == resolved or root in resolved.parents for root in roots):
        raise ValueError("Keep the inbound secret outside the central repository and Mac agent workspace.")
    return destination


def ensure_agent(client, config, name, remote_fs, secret_path):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name) or name in ("master", "built-in"):
        raise ValueError("Use one dedicated Mac node name.")
    if (not remote_fs.startswith("/") or ".." in PurePosixPath(remote_fs).parts
            or any(ord(c) < 32 for c in remote_fs)
            or remote_fs in ("/", "/Users", "/Applications", "/opt", "/tmp", "/var")
            or len(PurePosixPath(remote_fs).parts) < 3):
        raise ValueError("remote-fs must be a dedicated absolute Mac workspace path, without traversal.")
    destination = secret_destination(secret_path, remote_fs)
    label = config["parameters"]["MACOS_AGENT_LABEL"]
    path = "computer/" + urllib.parse.quote(name, safe="") + "/"
    ownership = f"Managed by flutter-cicd-central; project_id={config['project_id']}"
    try:
        _, body, _ = client.request("GET", path + "config.xml")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        node = {"name": name, "nodeDescription": ownership, "numExecutors": "1",
                "remoteFS": remote_fs, "labelString": label,
                "mode": "EXCLUSIVE", "type": "hudson.slaves.DumbSlave",
                "retentionStrategy": {"stapler-class": "hudson.slaves.RetentionStrategy$Always"},
                "launcher": {"stapler-class": "hudson.slaves.JNLPLauncher", "webSocket": True},
                "nodeProperties": {"stapler-class-bag": "true"}}
        form = urllib.parse.urlencode({"name": name, "type": "hudson.slaves.DumbSlave", "json": json.dumps(node)})
        client.acquire_crumb()
        try:
            client.request("POST", "computer/doCreateItem", form.encode(), "application/x-www-form-urlencoded")
        except urllib.error.HTTPError as created:
            if created.code != 302:
                raise
        _, body, _ = client.request("GET", path + "config.xml")
    xml = ET.fromstring(body)
    expected = {"description": ownership, "remoteFS": remote_fs, "numExecutors": "1",
                "mode": "EXCLUSIVE", "label": label}
    if any(xml.findtext(key) != value for key, value in expected.items()):
        raise ValueError("Existing Mac node differs or belongs to another setup; inspect it instead of overwriting.")
    launcher = xml.find("launcher")
    if launcher is None or launcher.get("class") != "hudson.slaves.JNLPLauncher" or launcher.findtext("webSocket") != "true":
        raise ValueError("Mac node must use the inbound WebSocket launcher.")
    _, jnlp, _ = client.request("GET", path + "jenkins-agent.jnlp")
    args = ET.fromstring(jnlp).findall("./application-desc/argument")
    if len(args) < 2 or args[1].text != name or not args[0].text:
        raise ValueError("Unexpected Jenkins agent secret response.")
    secret = args[0].text
    if not re.fullmatch(r"[A-Za-z0-9]+", secret):
        raise ValueError("Unexpected inbound secret format.")
    destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(secret + "\n")
    print("Owned Mac node verified; inbound secret saved to the requested protected file.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--agent-name", required=True)
    parser.add_argument("--remote-fs", required=True)
    parser.add_argument("--secret-file", required=True)
    args = parser.parse_args()
    config = read_config(args.config)
    if config["parameters"]["PLATFORM"] not in ("ios", "all"):
        raise ValueError("iOS was not selected.")
    user, token = os.environ.get("JENKINS_USER"), os.environ.get("JENKINS_API_TOKEN")
    if not user or not token:
        raise ValueError("Use protected JENKINS_USER/JENKINS_API_TOKEN environment bindings.")
    ensure_agent(Client(config["jenkins"]["url"], user, token), config, args.agent_name,
                 args.remote_fs, args.secret_file)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        print(f"ERROR: Jenkins HTTP {error.code}; verify administrative access.", file=sys.stderr)
        sys.exit(1)
    except (ValueError, KeyError, OSError, ET.ParseError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
