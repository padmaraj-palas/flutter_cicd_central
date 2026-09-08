#!/usr/bin/env python3
"""Native iOS build. All Apple credentials come from Jenkins bindings or an existing keychain."""
import argparse
import contextlib
import os
from pathlib import Path
import plistlib
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile

CENTRAL = Path(__file__).resolve().parents[1]

def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)

def quiet(args, **kwargs):
    # Never echo security arguments or output: certificate passwords may be present.
    result = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        raise ValueError("Apple signing/keychain operation failed; verify the Jenkins signing credentials.")
    return result.stdout

def settings(release):
    keys = ("ENVIRONMENT", "APP_NAME", "IOS_BUNDLE_ID")
    values = {key: os.environ.get(key, "") for key in keys}
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", values["ENVIRONMENT"]):
        raise ValueError("ENVIRONMENT must be a safe lowercase name.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}", values["APP_NAME"]):
        raise ValueError("APP_NAME must use 1-80 letters, digits, spaces, dots, underscores or hyphens.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+", values["IOS_BUNDLE_ID"]):
        raise ValueError("IOS_BUNDLE_ID must be an explicit reverse-domain bundle ID.")
    if os.environ.get("API_BASE_URL"):
        values["API_BASE_URL"] = os.environ["API_BASE_URL"]
    signing = {"team_id": os.environ.get("IOS_TEAM_ID", ""),
               "export_method": os.environ.get("IOS_EXPORT_METHOD", ""),
               "signing_style": os.environ.get("IOS_SIGNING_STYLE", ""),
               "provisioning_profile": os.environ.get("IOS_PROFILE_NAME", ""),
               "code_sign_identity": os.environ.get("IOS_CODE_SIGN_IDENTITY", ""),
               "release_signing": os.environ.get("IOS_RELEASE_SIGNING", "")}
    if release:
        if signing["release_signing"] not in ("jenkins", "existing-keychain"):
            raise ValueError("IOS_RELEASE_SIGNING must be jenkins or existing-keychain.")
        if not re.fullmatch(r"[A-Z0-9]{10}", signing["team_id"]):
            raise ValueError("Set IOS_TEAM_ID to your 10-character Apple team ID.")
        if signing["export_method"] not in ("app-store-connect", "release-testing", "debugging", "enterprise"):
            raise ValueError("Unsupported IOS_EXPORT_METHOD.")
        if signing["signing_style"] not in ("manual", "automatic"):
            raise ValueError("IOS_SIGNING_STYLE must be manual or automatic.")
        if signing["signing_style"] == "manual" and not signing["provisioning_profile"]:
            raise ValueError("Manual signing requires IOS_PROFILE_NAME.")
        if signing["code_sign_identity"] not in ("Apple Distribution", "Apple Development"):
            raise ValueError("IOS_CODE_SIGN_IDENTITY must be Apple Distribution or Apple Development.")
    return values, signing

@contextlib.contextmanager
def signing_session(signing, bundle_id):
    credentials = [os.environ.get(k) for k in ("IOS_P12_FILE", "IOS_P12_PASSWORD", "IOS_PROFILE_FILE")]
    if signing["release_signing"] == "jenkins" and not all(credentials):
        raise ValueError("Jenkins iOS signing requires all three credential bindings.")
    if signing["release_signing"] == "existing-keychain" and any(credentials):
        raise ValueError("Existing-keychain mode must not receive Jenkins signing bindings.")
    if not any(credentials):
        yield None
        return
    if not all(credentials):
        raise ValueError("All three iOS signing bindings are required.")
    if signing["signing_style"] != "manual":
        raise ValueError("Jenkins certificate/profile bindings require manual signing.")
    p12, password, profile = credentials
    decoded = plistlib.loads(quiet(["security", "cms", "-D", "-i", profile]))
    if signing["team_id"] not in decoded.get("TeamIdentifier", []):
        raise ValueError("Provisioning profile has the wrong Apple team.")
    if decoded.get("Name") != signing["provisioning_profile"]:
        raise ValueError("Provisioning profile Name does not match IOS_PROFILE_NAME.")
    application = decoded.get("Entitlements", {}).get("application-identifier", "")
    if application != f"{signing['team_id']}.{bundle_id}":
        raise ValueError("Use an explicit provisioning profile for this environment's bundle ID.")
    uuid = decoded.get("UUID", "")
    if not re.fullmatch(r"[A-Fa-f0-9-]+", uuid):
        raise ValueError("Invalid provisioning profile UUID.")
    # Serialize shared keychain search-list/profile changes across jobs on this account.
    import fcntl  # Available on the native Mac; portable contract tests do not need it.
    lock_dir = Path.home() / ".flutter-cicd"
    lock_dir.mkdir(mode=0o700, exist_ok=True)
    with (lock_dir / "signing.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix="flutter-cicd-signing-") as tmp:
            keychain = Path(tmp) / "build.keychain-db"
            keypass = secrets.token_urlsafe(32)
            old_list = shlex.split(quiet(["security", "list-keychains", "-d", "user"]).decode())
            # Xcode 16+ location and legacy location, preserving any identical installed profile.
            destinations = [
                Path.home() / "Library/Developer/Xcode/UserData/Provisioning Profiles" / f"{uuid}.mobileprovision",
                Path.home() / "Library/MobileDevice/Provisioning Profiles" / f"{uuid}.mobileprovision",
            ]
            created = []
            try:
                quiet(["security", "create-keychain", "-p", keypass, keychain])
                quiet(["security", "set-keychain-settings", "-lut", "21600", keychain])
                quiet(["security", "unlock-keychain", "-p", keypass, keychain])
                quiet(["security", "import", p12, "-k", keychain, "-P", password, "-T", "/usr/bin/codesign", "-T", "/usr/bin/security"])
                quiet(["security", "set-key-partition-list", "-S", "apple-tool:,apple:,codesign:", "-s", "-k", keypass, keychain])
                quiet(["security", "list-keychains", "-d", "user", "-s", keychain, *old_list])
                content = Path(profile).read_bytes()
                for destination in destinations:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists():
                        if destination.read_bytes() != content:
                            raise ValueError("A different provisioning profile already uses this UUID; refusing to replace it.")
                    else:
                        with destination.open("xb") as output:
                            created.append(destination)
                            os.chmod(destination, 0o600)
                            output.write(content)
                yield keychain
            finally:
                for destination in created:
                    destination.unlink(missing_ok=True)
                try:
                    quiet(["security", "list-keychains", "-d", "user", "-s", *old_list])
                finally:
                    if keychain.exists():
                        quiet(["security", "delete-keychain", keychain])

def verify_app(app, values, simulator):
    with (app / "Info.plist").open("rb") as source:
        info = plistlib.load(source)
    if info.get("CFBundleIdentifier") != values["IOS_BUNDLE_ID"] or info.get("CFBundleDisplayName") != values["APP_NAME"]:
        raise ValueError("Built iOS bundle ID/display name does not match the selected environment.")
    supported = info.get("CFBundleSupportedPlatforms", [])
    expected = "iPhoneSimulator" if simulator else "iPhoneOS"
    if expected not in supported:
        raise ValueError(f"Artifact is not for {expected}.")
    executable = info.get("CFBundleExecutable", "")
    if not executable or Path(executable).name != executable or not (app / executable).is_file():
        raise ValueError("Built app is missing its executable.")

def one_app(directory):
    apps = list(directory.glob("*.app"))
    if len(apps) != 1:
        raise ValueError(f"Expected one app in {directory}.")
    return apps[0]

def build(project):
    root = Path(project).resolve()
    if not (root / "pubspec.yaml").is_file() or not (root / "ios/Runner.xcodeproj").is_dir():
        raise ValueError("Expected a Flutter project with ios/Runner.xcodeproj.")
    # Do not follow app-provided build links outside the disposable checkout.
    for relative in ("build", "build/ci", "build/ios"):
        location = root / relative
        if location.is_symlink() or not location.resolve().is_relative_to(root):
            raise ValueError("Build outputs must stay inside the disposable checkout.")
    mode = os.environ.get("BUILD_MODE", "")
    if mode not in ("debug", "release"):
        raise ValueError("BUILD_MODE must be debug or release.")
    if sys.platform != "darwin":
        raise ValueError("iOS requires native macOS and Xcode.")
    values, signing = settings(mode == "release")
    environment = values["ENVIRONMENT"]
    scheme = os.environ.get("IOS_SCHEME", "Runner") or "Runner"
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", scheme):
        raise ValueError("IOS_SCHEME must name an existing shared scheme.")
    flavor = ["--flavor", scheme] if scheme != "Runner" else []
    # Credentials are available only to the signing helper, never application commands.
    child_env = os.environ.copy()
    for key in ("IOS_P12_FILE", "IOS_P12_PASSWORD", "IOS_PROFILE_FILE"):
        child_env.pop(key, None)
    child_env["BUNDLE_GEMFILE"] = str(CENTRAL / "Gemfile")
    output = root / f"build/ci/{environment}/{mode}/ios"
    if not output.resolve().is_relative_to(root):
        raise ValueError("Artifact output escaped the disposable checkout.")
    output.mkdir(parents=True, exist_ok=True)
    for name in ("SUCCESS", "app.zip", "app.ipa"):
        (output / name).unlink(missing_ok=True)
    run(["xcodebuild", "-version"])
    run(["xcrun", "--sdk", "iphonesimulator" if mode == "debug" else "iphoneos", "--show-sdk-path"])
    run(["bundle", "exec", "ruby", CENTRAL / "scripts/prepare-ios.rb", root], cwd=root, env=child_env)
    defines = [f"--dart-define={key}={values[key]}" for key in ("ENVIRONMENT", "APP_NAME", "API_BASE_URL") if key in values]
    if mode == "debug":
        # Clean native output so stale artifacts can never satisfy a successful no-op build.
        simulator = root / "build/ios/iphonesimulator"
        if simulator.exists():
            shutil.rmtree(simulator)
        run(["flutter", "build", "ios", "--simulator", "--debug", "--no-codesign", "--no-pub",
             *flavor, *defines], cwd=root, env=child_env)
        app = one_app(simulator)
        verify_app(app, values, True)
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, output / "app.zip"])
    else:
        with signing_session(signing, values["IOS_BUNDLE_ID"]) as keychain:
            # Xcode command-line build settings avoid persisting signing state in the native project.
            # Flutter forwards these environment settings via its generated xcconfig.
            config = {
                "method": signing["export_method"], "teamID": signing["team_id"],
                "signingStyle": signing["signing_style"], "destination": "export",
                "manageAppVersionAndBuildNumber": False,
            }
            if signing["signing_style"] == "manual":
                config["provisioningProfiles"] = {values["IOS_BUNDLE_ID"]: signing["provisioning_profile"]}
                config["signingCertificate"] = signing["code_sign_identity"]
            with tempfile.TemporaryDirectory(prefix="flutter-cicd-export-") as tmp:
                export = Path(tmp) / "ExportOptions.plist"
                export.write_bytes(plistlib.dumps(config))
                for folder in ("archive", "ipa"):
                    path = root / "build/ios" / folder
                    if path.exists():
                        shutil.rmtree(path)
                # XCODE_XCCONFIG_FILE is consumed by xcodebuild and has command-wide precedence.
                overrides = Path(tmp) / "Signing.xcconfig"
                def literal(value):
                    if not isinstance(value, str) or any(c in value for c in '\r\n"$\\'):
                        raise ValueError("Invalid signing build setting.")
                    return '"' + value + '"'
                content = f"DEVELOPMENT_TEAM = {literal(signing['team_id'])}\nCODE_SIGN_STYLE = {signing['signing_style'].capitalize()}\n"
                if signing["signing_style"] == "manual":
                    content += f"PROVISIONING_PROFILE_SPECIFIER = {literal(signing['provisioning_profile'])}\nCODE_SIGN_IDENTITY = {literal(signing['code_sign_identity'])}\n"
                if keychain:
                    content += f"OTHER_CODE_SIGN_FLAGS = --keychain {literal(str(keychain))}\n"
                overrides.write_text(content)
                env = child_env.copy()
                env["XCODE_XCCONFIG_FILE"] = str(overrides)
                # Do not pass credential bindings to Flutter or arbitrary app build phases.
                for key in ("IOS_P12_FILE", "IOS_P12_PASSWORD", "IOS_PROFILE_FILE"):
                    env.pop(key, None)
                run(["flutter", "build", "ipa", "--release", "--no-pub", *flavor,
                     f"--export-options-plist={export}", *defines], cwd=root, env=env)
                artifacts = list((root / "build/ios/ipa").glob("*.ipa"))
                if len(artifacts) != 1:
                    raise ValueError("Signed IPA export is missing or ambiguous (Flutter can finish after an export failure).")
                extract = Path(tmp) / "ipa"
                with zipfile.ZipFile(artifacts[0]) as archive:
                    for name in archive.namelist():
                        if name.startswith("/") or ".." in Path(name).parts:
                            raise ValueError("Invalid IPA member path.")
                run(["ditto", "-x", "-k", artifacts[0], extract])
                app = one_app(extract / "Payload")
                verify_app(app, values, False)
                run(["codesign", "--verify", "--deep", "--strict", app])
                shutil.copy2(artifacts[0], output / "app.ipa")
    (output / "SUCCESS").write_text("verified\n")
    print(f"Verified iOS {mode} artifact: {output}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        build(args.project)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        # CalledProcessError for security calls is never propagated (quiet() redacts it).
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
