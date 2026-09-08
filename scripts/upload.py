#!/usr/bin/env python3
"""Upload only verified central artifacts; never execute application checkout code."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from upload_settings import validate

CENTRAL = Path(__file__).resolve().parents[1]
# Explicit allowlist excludes signing secrets and ambient service credentials/config.
HOST_ENV = ("PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG", "LC_ALL", "JAVA_HOME", "DEVELOPER_DIR", "SSL_CERT_FILE", "SSL_CERT_DIR", "GEM_HOME", "GEM_PATH", "BUNDLE_PATH")


def artifact_path(project, values, platform):
    root = Path(project)
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("--project must be an absolute disposable checkout directory.")
    root = root.resolve()
    if root == CENTRAL or root.is_relative_to(CENTRAL) or CENTRAL.is_relative_to(root):
        raise ValueError("Upload checkout must be separate from central tooling.")
    environment, mode = values.get("ENVIRONMENT"), values.get("BUILD_MODE")
    if environment not in ("testing", "staging", "production") or mode not in ("debug", "release"):
        raise ValueError("Invalid upload environment or build mode.")
    folder = root / "build" / "ci" / environment / mode / platform
    suffix = "aab" if platform == "android" and mode == "release" else "apk" if platform == "android" else "ipa"
    artifact = folder / f"app.{suffix}"
    marker = folder / "SUCCESS"
    for path in (artifact, marker):
        if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in (path, *path.parents) if p != root and p.is_relative_to(root)):
            raise ValueError("Upload artifacts must not use symlinks or escape the checkout.")
        if not path.is_file() or not path.stat().st_size:
            raise ValueError("Upload requires a nonempty artifact and SUCCESS marker.")
    if marker.read_text(encoding="utf-8") != f"{environment} {mode} {platform}\n":
        raise ValueError("SUCCESS marker does not match this environment, mode and platform.")
    return artifact


def credential_file(environ, key):
    value = environ.get(key, "")
    path = Path(value)
    if not value or not path.is_absolute() or not path.is_file() or not path.stat().st_size:
        raise ValueError(f"{key} must bind a nonempty Jenkins secret JSON file.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as error:
        raise ValueError(f"{key} must contain valid JSON.") from error
    fields = ("key_id", "issuer_id", "key") if key == "APPSTORE_API_KEY_FILE" else ("type", "project_id", "client_email", "private_key")
    if not isinstance(data, dict) or any(not isinstance(data.get(field), str) or not data[field] for field in fields):
        raise ValueError(f"{key} is missing required credential fields.")
    if key != "APPSTORE_API_KEY_FILE" and data["type"] != "service_account":
        raise ValueError(f"{key} must contain a service-account JSON key.")
    return str(path.resolve())


def upload(project, platform, environ=None):
    environ = os.environ if environ is None else environ
    values = validate(environ)
    if platform not in ("android", "ios", "web") or values["PLATFORM"] not in (platform, "all"):
        raise ValueError("Upload platform must be selected by the job.")
    destination = values[f"{platform.upper()}_UPLOAD_DESTINATION"]
    if destination == "none":
        print(f"{platform}: upload disabled.")
        return
    artifact = artifact_path(project, values, platform)
    binding = {"firebase": "FIREBASE_CREDENTIALS_FILE", "google": "GOOGLE_PLAY_CREDENTIALS_FILE", "appstore": "APPSTORE_API_KEY_FILE"}[destination]
    credential = credential_file(environ, binding)
    with tempfile.TemporaryDirectory(prefix="central-upload-") as temporary:
        work = Path(temporary)
        child = {key: environ[key] for key in HOST_ENV if environ.get(key)}
        child.setdefault("LANG", "en_US.UTF-8")
        child.update(HOME=str(work), USERPROFILE=str(work), XDG_CONFIG_HOME=str(work / "config"), CI="true", FASTLANE_OPT_OUT_USAGE="1", FASTLANE_SKIP_UPDATE_CHECK="1", FASTLANE_DISABLE_COLORS="1")
        if destination == "firebase":
            child["GOOGLE_APPLICATION_CREDENTIALS"] = credential
            command = ["firebase", "appdistribution:distribute", str(artifact), "--app", values[f"FIREBASE_{platform.upper()}_APP_ID"], "--non-interactive"]
            if values["FIREBASE_GROUPS"]:
                command += ["--groups", values["FIREBASE_GROUPS"]]
            if values["UPLOAD_RELEASE_NOTES"]:
                notes = work / "notes.txt"
                notes.write_text(values["UPLOAD_RELEASE_NOTES"], encoding="utf-8")
                command += ["--release-notes-file", str(notes)]
        else:
            child.update({key: values.get(key, "") for key in ("ANDROID_APPLICATION_ID", "IOS_BUNDLE_ID", "GOOGLE_PLAY_TRACK", "GOOGLE_PLAY_RELEASE_STATUS", "UPLOAD_RELEASE_NOTES")})
            (work / "metadata").mkdir()
            child[binding] = credential
            child.update(BUNDLE_GEMFILE=str(CENTRAL / "upload/Gemfile"), BUNDLE_FROZEN="true", CI_UPLOAD_DESTINATION=destination, CI_UPLOAD_ARTIFACT=str(artifact), CI_UPLOAD_METADATA=str(work / "metadata"))
            if destination == "google" and values["UPLOAD_RELEASE_NOTES"]:
                changelogs = work / "metadata/en-US/changelogs"
                changelogs.mkdir(parents=True)
                (changelogs / "default.txt").write_text(values["UPLOAD_RELEASE_NOTES"], encoding="utf-8")
            command = ["bundle", "exec", "ruby", str(CENTRAL / "upload/run.rb")]
        # Service tools may print key material in diagnostics. Do not forward their output.
        try:
            subprocess.run(command, cwd=work, env=child, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError as error:
            raise ValueError(f"Upload tool is missing for {destination}; provision the central upload dependencies.") from error
        except subprocess.CalledProcessError as error:
            raise ValueError(f"{destination} upload failed (exit {error.returncode}); check service access, signing, app registration and version uniqueness. Tool output was suppressed to protect credentials.") from error
    print(f"{platform}: {destination} accepted the upload command; processing/review may still be pending.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "upload"))
    parser.add_argument("--project")
    parser.add_argument("--platform", choices=("android", "ios", "web"))
    args = parser.parse_args()
    try:
        if args.action == "validate":
            validate(os.environ)
            print("Upload settings validated.")
        else:
            if not args.project or not args.platform:
                raise ValueError("upload requires --project and --platform.")
            upload(args.project, args.platform)
    except (ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
