#!/usr/bin/env python3
"""Configure one central Flutter Jenkins job without writing to the Flutter repository."""
import argparse
import base64
from datetime import datetime, timezone
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET

# Shared upload contract lives with the central runtime, never in an app checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import upload_settings

CHOICES = {
    "ENVIRONMENT": ("testing", "staging", "production"),
    "BUILD_MODE": ("debug", "release"),
    "PLATFORM": ("android", "web", "ios", "all"),
    "IOS_RELEASE_SIGNING": ("jenkins", "existing-keychain"),
    "ANDROID_RELEASE_SIGNING": ("jenkins", "project"),
    "IOS_EXPORT_METHOD": ("app-store-connect", "release-testing", "debugging", "enterprise"),
    "IOS_SIGNING_STYLE": ("manual", "automatic"),
    "IOS_CODE_SIGN_IDENTITY": ("Apple Distribution", "Apple Development"),
}
CHOICES.update(upload_settings.CHOICES)
PARAMETERS = (
    "APP_REPOSITORY_URL", "APP_BRANCH", "APP_CREDENTIALS_ID",
    "ENVIRONMENT", "BUILD_MODE", "PLATFORM", "APP_NAME", "API_BASE_URL",
    "ANDROID_APPLICATION_ID", "IOS_BUNDLE_ID", "ANDROID_FLAVOR", "IOS_SCHEME",
    "LINUX_AGENT_LABEL", "MACOS_AGENT_LABEL", "FLUTTER_IMAGE",
    "ANDROID_RELEASE_SIGNING", "ANDROID_KEYSTORE_CREDENTIAL_ID",
    "ANDROID_STORE_PASSWORD_CREDENTIAL_ID", "ANDROID_KEY_ALIAS_CREDENTIAL_ID",
    "ANDROID_KEY_PASSWORD_CREDENTIAL_ID",
    "IOS_RELEASE_SIGNING", "IOS_TEAM_ID", "IOS_EXPORT_METHOD", "IOS_SIGNING_STYLE",
    "IOS_PROFILE_NAME", "IOS_CODE_SIGN_IDENTITY", "IOS_P12_CREDENTIAL_ID",
    "IOS_PASSWORD_CREDENTIAL_ID", "IOS_PROFILE_CREDENTIAL_ID",
) + tuple(upload_settings.DEFAULTS)
CREDENTIALS = ("APP_CREDENTIALS_ID", "IOS_P12_CREDENTIAL_ID",
               "IOS_PASSWORD_CREDENTIAL_ID", "IOS_PROFILE_CREDENTIAL_ID",
               "ANDROID_KEYSTORE_CREDENTIAL_ID", "ANDROID_STORE_PASSWORD_CREDENTIAL_ID",
               "ANDROID_KEY_ALIAS_CREDENTIAL_ID", "ANDROID_KEY_PASSWORD_CREDENTIAL_ID") + upload_settings.CREDENTIALS


UPLOAD_DESCRIPTIONS = {
    "ANDROID_UPLOAD_DESTINATION": "none archives only; firebase distributes to Firebase; google uploads a release AAB to Google Play.",
    "IOS_UPLOAD_DESTINATION": "none archives only; firebase distributes a signed IPA; appstore uploads to App Store Connect/TestFlight without submitting for review.",
    "WEB_UPLOAD_DESTINATION": "none archives only; web deployment is not yet available.",
    "GOOGLE_PLAY_TRACK": "Google Play release track. Used only when Android upload destination is google.",
    "GOOGLE_PLAY_RELEASE_STATUS": "draft saves a draft release; completed rolls out to the selected track.",
    "FIREBASE_ANDROID_APP_ID": "Public Firebase Android app ID from Project settings (1:project-number:android:app-id).",
    "FIREBASE_IOS_APP_ID": "Public Firebase iOS app ID from Project settings (1:project-number:ios:app-id).",
    "FIREBASE_GROUPS": "Optional comma-separated Firebase tester group aliases, without spaces.",
    "FIREBASE_CREDENTIALS_ID": "Jenkins Secret file credential ID for Firebase service-account JSON; never enter the JSON here.",
    "GOOGLE_PLAY_CREDENTIALS_ID": "Jenkins Secret file credential ID for Google Play service-account JSON; never enter the JSON here.",
    "APPSTORE_API_KEY_CREDENTIALS_ID": "Jenkins Secret file credential ID for Fastlane App Store Connect API-key JSON; never enter the JSON here.",
    "UPLOAD_RELEASE_NOTES": "Optional public release notes, single line, at most 500 characters. Do not enter secrets.",
}


def fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{label}: supply exactly the documented public fields; never put secrets in answers.")


def literal(value, label, empty=False):
    if (not isinstance(value, str) or (not value and not empty)
            or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError(f"{label}: use a single-line string without surrounding whitespace.")


def repository(value, label):
    literal(value, label)
    if re.search(r"\s", value):
        raise ValueError(f"{label}: whitespace is not allowed.")
    if re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[A-Za-z0-9._/-]+", value):
        return
    https = r"https://[A-Za-z0-9.-]+(?::[0-9]+)?/[A-Za-z0-9._/-]+"
    ssh = r"ssh://[A-Za-z0-9._-]+@[A-Za-z0-9.-]+(?::[0-9]+)?/[A-Za-z0-9._/-]+"
    if not (re.fullmatch(https, value) or re.fullmatch(ssh, value)):
        raise ValueError(f"{label}: use a literal HTTPS URL or SSH URL with an explicit user; no secrets, query or fragment.")
    parsed = urllib.parse.urlsplit(value)
    if not parsed.hostname or parsed.path == "/" or (parsed.port is not None and not 1 <= parsed.port <= 65535):
        raise ValueError(f"{label}: invalid repository host, port or path.")


def ref(value, label, branch_only=False):
    literal(value, label)
    if (not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", value)
            or any(part.startswith(".") or part.endswith(".lock") for part in value.split("/"))
            or ".." in value or "//" in value or value.endswith(("/", "."))):
        raise ValueError(f"{label}: use one explicit Git branch or refs/tags/<tag>; no wildcards.")
    if branch_only and value.startswith("refs/") and not value.startswith("refs/heads/"):
        raise ValueError(f"{label}: the application must track a branch, not a tag or pull-request ref.")
    if not branch_only and value.startswith("refs/") and not value.startswith(("refs/heads/", "refs/tags/")):
        raise ValueError(f"{label}: use a branch or refs/tags/<tag>.")


def docker_image(value):
    parts = value.split("@")
    if len(parts) > 2 or (len(parts) == 2 and not re.fullmatch(r"sha256:[a-f0-9]{64}", parts[1])):
        raise ValueError("FLUTTER_IMAGE: use a Docker image tag or sha256 digest, without credentials.")
    components = parts[0].split("/")
    final = components[-1].split(":")
    if len(final) > 2 or (len(final) == 2 and not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", final[1])):
        raise ValueError("FLUTTER_IMAGE: invalid Docker image tag.")
    names = components[:-1] + [final[0]]
    if len(names) > 1 and ":" in names[0]:
        host, separator, port = names[0].rpartition(":")
        if not re.fullmatch(r"[a-z0-9.-]+", host) or not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError("FLUTTER_IMAGE: invalid registry host/port.")
        names = names[1:]
    if any(not re.fullmatch(r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*", name) for name in names):
        raise ValueError("FLUTTER_IMAGE: use a Docker image reference without flags, whitespace or credentials.")


def cron(value):
    literal(value, "jenkins.poll_schedule", empty=True)
    if not value:
        return
    if value in ("@yearly", "@annually", "@monthly", "@weekly", "@daily", "@midnight", "@hourly"):
        return
    parts = value.split()
    if len(parts) != 5:
        raise ValueError("jenkins.poll_schedule: use a five-field Jenkins cron expression or an empty string.")
    for part, (low, high) in zip(parts, ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))):
        for term in part.split(","):
            match = re.fullmatch(r"(\*|H(?:\((\d+)-(\d+)\))?|(\d+)(?:-(\d+))?)(?:/(\d+))?", term)
            if not match:
                raise ValueError("jenkins.poll_schedule: unsupported cron syntax.")
            _, hstart, hend, start, end, step = match.groups()
            first, last = hstart or start, hend or end or start
            if first and not low <= int(first) <= int(last) <= high:
                raise ValueError("jenkins.poll_schedule: cron value is outside its field range.")
            if step and int(step) < 1:
                raise ValueError("jenkins.poll_schedule: cron step must be positive.")


def validate(data):
    fields(data, ("schema_version", "confirmed", "project_id", "job_name", "jenkins", "ci", "parameters"), "answers")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["confirmed"] is not True:
        raise ValueError("Confirm the collected settings before use: schema_version=1, confirmed=true.")
    for name, pattern, characters in (
        ("project_id", r"[A-Za-z][A-Za-z0-9_.-]{0,79}", "letters, digits, dots, underscores or hyphens"),
        ("job_name", r"[A-Za-z][A-Za-z0-9 ._-]{0,79}", "letters, digits, spaces, dots, underscores or hyphens"),
    ):
        literal(data[name], name)
        if not re.fullmatch(pattern, data[name]):
            raise ValueError(f"{name}: start with a letter and use at most 80 {characters}.")
    fields(data["jenkins"], ("url", "poll_schedule"), "jenkins")
    literal(data["jenkins"]["url"], "jenkins.url")
    url = urllib.parse.urlsplit(data["jenkins"]["url"])
    if (url.scheme not in ("http", "https") or not url.hostname or url.username
            or url.password or url.query or url.fragment):
        raise ValueError("jenkins.url: use an HTTP(S) Jenkins base URL without credentials, query or fragment.")
    cron(data["jenkins"]["poll_schedule"])
    fields(data["ci"], ("repository_url", "ref", "script_path", "credentials_id"), "ci")
    ci = data["ci"]
    repository(ci["repository_url"], "ci.repository_url")
    ref(ci["ref"], "ci.ref")
    literal(ci["script_path"], "ci.script_path")
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", ci["script_path"])
            or any(part in (".", "..") for part in ci["script_path"].split("/"))):
        raise ValueError("ci.script_path: use a repository-relative Jenkinsfile path without traversal.")
    literal(ci["credentials_id"], "ci.credentials_id", empty=True)
    if not re.fullmatch(r"[A-Za-z0-9_.-]*", ci["credentials_id"]):
        raise ValueError("ci.credentials_id: provide a Jenkins credential ID, not its secret.")
    p = data["parameters"]
    # Existing answer files remain build-only until upload settings are supplied.
    if isinstance(p, dict):
        for key, value in upload_settings.DEFAULTS.items():
            p.setdefault(key, value)
    fields(p, PARAMETERS, "parameters")
    for key in PARAMETERS:
        literal(p[key], key, empty=key in upload_settings.DEFAULTS or key in CREDENTIALS or key in (
            "ANDROID_FLAVOR", "IOS_SCHEME", "IOS_TEAM_ID", "IOS_PROFILE_NAME"))
    for key, choices in CHOICES.items():
        if p[key] not in choices:
            raise ValueError(f"{key}: choose one of {', '.join(choices)}.")
    repository(p["APP_REPOSITORY_URL"], "APP_REPOSITORY_URL")
    ref(p["APP_BRANCH"], "APP_BRANCH", branch_only=True)
    for key in CREDENTIALS:
        if not re.fullmatch(r"[A-Za-z0-9_.-]*", p[key]):
            raise ValueError(f"{key}: provide a Jenkins credential ID, never the credential value.")
    for key in ("LINUX_AGENT_LABEL", "MACOS_AGENT_LABEL"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", p[key]):
            raise ValueError(f"{key}: use one literal Jenkins node label.")
    if p["PLATFORM"] in ("ios", "all") and p["MACOS_AGENT_LABEL"] in ("built-in", "master"):
        raise ValueError("MACOS_AGENT_LABEL: use a dedicated native macOS agent label.")
    docker_image(p["FLUTTER_IMAGE"])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}", p["APP_NAME"]):
        raise ValueError("APP_NAME: use 1-80 letters, digits, spaces, dots, underscores or hyphens.")
    try:
        api = urllib.parse.urlsplit(p["API_BASE_URL"])
        _ = api.port
    except ValueError as error:
        raise ValueError("API_BASE_URL: use a valid public HTTP(S) URL and port.") from error
    forbidden_url_characters = (chr(96), "$", "\\", '"', "'", "<", ">")
    if (api.scheme not in ("https", "http") or not api.hostname or api.username or api.password
            or api.query or api.fragment or re.search(r"\s", p["API_BASE_URL"])
            or any(char in p["API_BASE_URL"] for char in forbidden_url_characters)):
        raise ValueError("API_BASE_URL: use a public HTTP(S) API base URL without credentials, interpolation, query or fragment.")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+", p["ANDROID_APPLICATION_ID"]):
        raise ValueError("ANDROID_APPLICATION_ID: use a dotted Android application ID.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+", p["IOS_BUNDLE_ID"]):
        raise ValueError("IOS_BUNDLE_ID: use a dotted Apple bundle ID.")
    for key in ("ANDROID_FLAVOR", "IOS_SCHEME"):
        if p[key] and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", p[key]):
            raise ValueError(f"{key}: use an existing simple flavor/scheme name or an empty string.")
    if p["IOS_TEAM_ID"] and not re.fullmatch(r"[A-Z0-9]{10}", p["IOS_TEAM_ID"]):
        raise ValueError("IOS_TEAM_ID: use Apple's ten-character uppercase team ID.")
    if any(c in p["IOS_PROFILE_NAME"] for c in ('"', "'", "\\", "$", chr(96))):
        raise ValueError("IOS_PROFILE_NAME: use the literal profile name without shell or configuration syntax.")
    signing_keys = ("IOS_P12_CREDENTIAL_ID", "IOS_PASSWORD_CREDENTIAL_ID", "IOS_PROFILE_CREDENTIAL_ID")
    if p["IOS_RELEASE_SIGNING"] == "existing-keychain" and any(p[key] for key in signing_keys):
        raise ValueError("Existing-keychain signing uses empty Jenkins certificate/password/profile credential IDs.")
    if p["PLATFORM"] in ("ios", "all") and p["BUILD_MODE"] == "release":
        if not p["IOS_TEAM_ID"]:
            raise ValueError("An iOS release requires IOS_TEAM_ID.")
        if p["IOS_SIGNING_STYLE"] == "manual" and not p["IOS_PROFILE_NAME"]:
            raise ValueError("Manual iOS release signing requires IOS_PROFILE_NAME.")
        if p["IOS_RELEASE_SIGNING"] == "jenkins":
            if not all(p[key] for key in signing_keys) or p["IOS_SIGNING_STYLE"] != "manual":
                raise ValueError("Jenkins iOS signing requires all three credential IDs and manual signing.")
    android_credentials = ("ANDROID_KEYSTORE_CREDENTIAL_ID", "ANDROID_STORE_PASSWORD_CREDENTIAL_ID",
                           "ANDROID_KEY_ALIAS_CREDENTIAL_ID", "ANDROID_KEY_PASSWORD_CREDENTIAL_ID")
    if p["ANDROID_RELEASE_SIGNING"] == "project" and any(p[key] for key in android_credentials):
        raise ValueError("Project Android signing uses empty central Jenkins Android signing credential IDs.")
    if (p["PLATFORM"] in ("android", "all") and p["BUILD_MODE"] == "release"
            and p["ANDROID_RELEASE_SIGNING"] == "jenkins" and not all(p[key] for key in android_credentials)):
        raise ValueError("Jenkins Android release signing requires all four credential IDs.")
    p.update(upload_settings.validate(p))
    return data


def read_config(path):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate answers field; keep exactly one value per setting.")
            result[key] = value
        return result
    return validate(json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=no_duplicates))


def child(parent, tag, value=None, **attributes):
    node = ET.SubElement(parent, tag, attributes)
    if value is not None:
        node.text = str(value)
    return node


def ownership(data):
    return f"Managed by flutter-cicd-central; project_id={data['project_id']}"


def job_xml(data):
    validate(data)
    root = ET.Element("flow-definition", {"plugin": "workflow-job"})
    child(root, "description", ownership(data))
    child(root, "keepDependencies", "false")
    properties = child(root, "properties")
    definitions = child(child(properties, "hudson.model.ParametersDefinitionProperty"), "parameterDefinitions")
    for name in PARAMETERS:
        value = data["parameters"][name]
        if name in CHOICES:
            parameter = child(definitions, "hudson.model.ChoiceParameterDefinition")
            child(parameter, "name", name)
            child(parameter, "description", UPLOAD_DESCRIPTIONS.get(name, "Saved setting for this job; edit Configure to change."))
            array = child(child(parameter, "choices", **{"class": "java.util.Arrays$ArrayList"}),
                          "a", **{"class": "string-array"})
            child(array, "string", value)
        else:
            parameter = child(definitions, "hudson.model.StringParameterDefinition")
            child(parameter, "name", name)
            child(parameter, "description", UPLOAD_DESCRIPTIONS.get(name, "Public setting / credential ID only. Do not enter a secret."))
            child(parameter, "defaultValue", value)
            child(parameter, "trim", "true")
    retention = child(child(properties, "jenkins.model.BuildDiscarderProperty"), "strategy",
                      **{"class": "hudson.tasks.LogRotator"})
    for key, value in (("daysToKeep", -1), ("numToKeep", 20), ("artifactDaysToKeep", -1), ("artifactNumToKeep", 20)):
        child(retention, key, value)
    triggers = child(child(properties, "org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty"),
                     "triggers")
    if data["jenkins"]["poll_schedule"]:
        trigger = child(triggers, "hudson.triggers.SCMTrigger")
        child(trigger, "spec", data["jenkins"]["poll_schedule"])
        child(trigger, "ignorePostCommitHooks", "false")
    definition = child(root, "definition", **{
        "class": "org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition", "plugin": "workflow-cps"})
    scm = child(definition, "scm", **{"class": "hudson.plugins.git.GitSCM", "plugin": "git"})
    child(scm, "configVersion", 2)
    remote = child(child(scm, "userRemoteConfigs"), "hudson.plugins.git.UserRemoteConfig")
    child(remote, "url", data["ci"]["repository_url"])
    if data["ci"]["credentials_id"]:
        child(remote, "credentialsId", data["ci"]["credentials_id"])
    selected_ref = data["ci"]["ref"]
    child(child(child(scm, "branches"), "hudson.plugins.git.BranchSpec"), "name",
          selected_ref if selected_ref.startswith("refs/") or re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", selected_ref) else "*/" + selected_ref)
    child(scm, "doGenerateSubmoduleConfigurations", "false")
    child(scm, "submoduleCfg", **{"class": "empty-list"})
    child(scm, "extensions")
    child(definition, "scriptPath", data["ci"]["script_path"])
    child(definition, "lightweight", "true")
    child(root, "disabled", "false")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_new(path, content):
    """Exclusive creation prevents replacing an existing file or following a destination symlink."""
    destination = Path(path)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, url, user, secret):
        self.url = url.rstrip("/") + "/"
        self.authorization = "Basic " + base64.b64encode((user + ":" + secret).encode()).decode()
        self.opener = urllib.request.build_opener(
            NoRedirect(), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.crumb = {}

    def request(self, method, path, data=None, content_type="application/xml"):
        if path.startswith("/") or "://" in path or ".." in path.split("/"):
            raise ValueError("Jenkins request must stay relative to the configured server.")
        headers = {"Authorization": self.authorization, "Content-Type": content_type, **self.crumb}
        request = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        with self.opener.open(request, timeout=30) as response:
            return response.status, response.read(), response.headers

    def acquire_crumb(self):
        try:
            _, body, _ = self.request("GET", "crumbIssuer/api/json")
            data = json.loads(body)
            self.crumb = {data["crumbRequestField"]: data["crumb"]}
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise


def require_owned(existing, data):
    parsed = ET.fromstring(existing)
    if parsed.tag != "flow-definition" or parsed.findtext("description") != ownership(data):
        raise ValueError("Refusing to modify or build an unrelated Jenkins job; choose a new job name.")


def ensure_job(client, data, backup_directory):
    path = "job/" + urllib.parse.quote(data["job_name"], safe="") + "/"
    try:
        _, existing, _ = client.request("GET", path + "config.xml")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        client.request("POST", "createItem?name=" + urllib.parse.quote(data["job_name"], safe=""), job_xml(data))
        return {"action": "created", "job_name": data["job_name"]}
    require_owned(existing, data)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = Path(backup_directory) / f"{data['job_name']}-before-{stamp}-{uuid.uuid4().hex[:8]}.xml"
    write_new(backup, existing)
    client.request("POST", path + "config.xml", job_xml(data))
    return {"action": "updated", "job_name": data["job_name"], "backup": str(backup)}


def build_job(client, data):
    path = "job/" + urllib.parse.quote(data["job_name"], safe="") + "/"
    _, existing, _ = client.request("GET", path + "config.xml")
    require_owned(existing, data)
    # Use the current saved settings, including later Jenkins UI edits.
    _, _, headers = client.request("POST", path + "buildWithParameters", b"",
                                   "application/x-www-form-urlencoded")
    location = headers.get("Location", "")
    match = re.search(r"/queue/item/([0-9]+)/?$", urllib.parse.urlsplit(location).path)
    return {"action": "queued", "job_name": data["job_name"],
            "queue_id": int(match.group(1)) if match else None}


def status_job(client, data, queue_id=None, build_number=None):
    path = "job/" + urllib.parse.quote(data["job_name"], safe="") + "/"
    if queue_id is not None:
        _, body, _ = client.request("GET", f"queue/item/{queue_id}/api/json?tree=id,cancelled,why,executable[number,url]")
    elif build_number is not None:
        _, body, _ = client.request("GET", path + f"{build_number}/api/json?tree=number,result,building,url,artifacts[fileName,relativePath]")
    else:
        _, body, _ = client.request("GET", path + "api/json?tree=name,url,buildable,lastBuild[number,result,building,url,artifacts[fileName,relativePath]]")
    return json.loads(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "render-job", "ensure-job", "build", "status"))
    parser.add_argument("--config", required=True, help="Confirmed public answers JSON.")
    parser.add_argument("--output", help="New XML file for render-job; existing files are never overwritten.")
    parser.add_argument("--backup-directory", help="Existing directory for job update backups; defaults beside answers.")
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument("--queue-id", type=int, help="For status: inspect the exact queued build.")
    selected.add_argument("--build-number", type=int, help="For status: inspect the exact build after queue assignment.")
    args = parser.parse_args()
    data = read_config(args.config)
    if args.action == "validate":
        print("Confirmed central job settings are valid. No Flutter project files were created.")
        return
    if args.action == "render-job":
        if not args.output:
            parser.error("--output is required for render-job")
        write_new(args.output, job_xml(data))
        print("Central Pipeline job XML rendered. Import or ensure the job, then run its first build to register app polling.")
        return
    if any(value is not None and value < 1 for value in (args.queue_id, args.build_number)):
        parser.error("Queue/build identifiers must be positive.")
    if args.action != "status" and (args.queue_id is not None or args.build_number is not None):
        parser.error("--queue-id/--build-number are available only for status")
    user, secret = os.environ.get("JENKINS_USER"), os.environ.get("JENKINS_API_TOKEN")
    if not user or not secret:
        raise ValueError("Provide JENKINS_USER and JENKINS_API_TOKEN through the protected process environment.")
    client = Client(data["jenkins"]["url"], user, secret)
    if args.action == "status":
        result = status_job(client, data, args.queue_id, args.build_number)
    else:
        client.acquire_crumb()
        if args.action == "ensure-job":
            result = ensure_job(client, data, args.backup_directory or Path(args.config).resolve().parent)
        else:
            result = build_job(client, data)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        print(f"ERROR: Jenkins HTTP {error.code}; check the configured server URL and permissions.", file=sys.stderr)
        sys.exit(1)
    except (ValueError, KeyError, OSError, ET.ParseError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
