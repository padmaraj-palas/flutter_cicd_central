#!/usr/bin/env python3
"""Build a disposable Flutter checkout using public Jenkins parameters only."""
import argparse
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import urlsplit

CENTRAL = Path(__file__).resolve().parents[1]
ANDROID_NS = "http://schemas.android.com/apk/res/android"
PUBLIC = ("ENVIRONMENT", "BUILD_MODE", "APP_NAME", "API_BASE_URL", "ANDROID_APPLICATION_ID", "IOS_BUNDLE_ID")


def settings(environ=None):
    env = os.environ if environ is None else environ
    values = {key: env.get(key, "") for key in PUBLIC}
    if values["ENVIRONMENT"] not in ("testing", "staging", "production"):
        raise ValueError("ENVIRONMENT must be testing, staging or production.")
    if values["BUILD_MODE"] not in ("debug", "release"):
        raise ValueError("BUILD_MODE must be debug or release.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}", values["APP_NAME"]):
        raise ValueError("APP_NAME must be 1-80 letters/digits, spaces, dots, underscores or hyphens, starting with a letter/digit.")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+", values["ANDROID_APPLICATION_ID"]):
        raise ValueError("ANDROID_APPLICATION_ID must be a dotted Android application ID.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+", values["IOS_BUNDLE_ID"]):
        raise ValueError("IOS_BUNDLE_ID must be a dotted Apple bundle ID.")
    url = values["API_BASE_URL"]
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError as error:
        raise ValueError("API_BASE_URL must be an absolute HTTP(S) URL.") from error
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
            or any(c.isspace() or ord(c) < 32 for c in url) or any(c in url for c in "`$\\\"'<>")):
        raise ValueError("API_BASE_URL must be an absolute public HTTP(S) URL without credentials or interpolation.")
    for key, default in (("ANDROID_FLAVOR", ""), ("IOS_SCHEME", "Runner")):
        value = env.get(key, default)
        if (not value and key == "IOS_SCHEME") or (value and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value)):
            raise ValueError(f"{key} must be a simple existing native flavor/scheme name.")
        values[key] = value
    return values


def project_path(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("--project must be an absolute disposable checkout path.")
    path = path.resolve()
    if path == CENTRAL or CENTRAL.is_relative_to(path) or path.is_relative_to(CENTRAL):
        raise ValueError("Flutter checkout must be separate from the central CI repository.")
    if not (path / "pubspec.yaml").is_file():
        raise ValueError("--project must contain pubspec.yaml.")
    return path


def inside(project, relative):
    path = project / relative
    if not path.resolve().is_relative_to(project):
        raise ValueError(f"Build path escapes disposable checkout: {relative}")
    return path


def run(args, project, **kwargs):
    return subprocess.run([str(arg) for arg in args], cwd=project, check=True, **kwargs)


def clean(project, relative):
    path = inside(project, relative)
    if path.is_symlink():
        raise ValueError(f"Refusing symlink output: {relative}")
    if path.exists():
        shutil.rmtree(path)


def quality(project):
    public_child = os.environ.copy()
    for credential in ("IOS_P12_FILE", "IOS_P12_PASSWORD", "IOS_PROFILE_FILE", "ANDROID_KEYSTORE_FILE", "ANDROID_STORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD"):
        public_child.pop(credential, None)
    run(["flutter", "pub", "get"], project, env=public_child)
    run(["dart", "format", "--output=none", "--set-exit-if-changed", "lib", *(["test"] if (project / "test").is_dir() else [])], project)
    run(["flutter", "analyze", "--no-pub"], project)
    if (project / "test").is_dir():
        run(["flutter", "test", "--no-pub"], project)
    else:
        print("No test/ directory; Flutter unit tests were not run.")


def prepare_web(project, name):
    index = inside(project, "web/index.html")
    content = index.read_text(encoding="utf-8")
    replacement = "<title>" + html.escape(name) + "</title>"
    content, count = re.subn(r"<title\b[^>]*>.*?</title>", lambda _: replacement, content, flags=re.I | re.S)
    if count != 1:
        raise ValueError("Expected exactly one title in web/index.html.")
    # Standard Flutter PWA metadata; avoid reconstructing arbitrary project HTML.
    content = re.sub(r'(<meta\s+name=[\"\']apple-mobile-web-app-title[\"\']\s+content=)[\"\'][^\"\']*[\"\']',
                     lambda m: m[1] + '"' + html.escape(name, quote=True) + '"', content, flags=re.I)
    manifest = inside(project, "web/manifest.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data.update(name=name, short_name=name)
    index.write_text(content, encoding="utf-8")
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def prepare_android(project, name):
    candidates = [inside(project, f"android/app/{file}") for file in ("build.gradle", "build.gradle.kts")]
    found = [p for p in candidates if p.is_file()]
    if len(found) != 1:
        raise ValueError("Expected one standard android/app/build.gradle or build.gradle.kts.")
    gradle = found[0]
    content = gradle.read_text(encoding="utf-8")
    marker = "// CENTRAL_FLUTTER_CI_IDENTITY"
    if marker in content:
        raise ValueError("Checkout already has central build edits; use a fresh checkout.")
    script = (CENTRAL / "scripts/android.gradle").as_posix()
    if any(char in script for char in ('"', '$', '\n', '\r')):
        raise ValueError("Central repository path contains unsupported Gradle interpolation characters.")
    statement = f'apply(from = "{script}")' if gradle.suffix == ".kts" else f'apply from: "{script}"'
    manifests = list(inside(project, "android/app/src").glob("*/AndroidManifest.xml"))
    main = inside(project, "android/app/src/main/AndroidManifest.xml")
    if main not in manifests:
        raise ValueError("Missing standard Android main manifest.")
    # Set main and every source-set overlay application label so a flavor cannot override it.
    for path in manifests:
        if not path.resolve().is_relative_to(project):
            raise ValueError("Manifest symlink escapes checkout.")
        document = ET.parse(path)
        application = document.getroot().find("application")
        if application is not None:
            application.set(f"{{{ANDROID_NS}}}label", name)
            for component in application:
                if component.tag not in ("activity", "activity-alias"):
                    continue
                launcher = any(category.get(f"{{{ANDROID_NS}}}name") == "android.intent.category.LAUNCHER"
                               for category in component.findall("intent-filter/category"))
                if launcher and f"{{{ANDROID_NS}}}label" in component.attrib:
                    component.set(f"{{{ANDROID_NS}}}label", name)
            ET.register_namespace("android", ANDROID_NS)
            ET.register_namespace("tools", "http://schemas.android.com/tools")
            document.write(path, encoding="utf-8", xml_declaration=True)
    gradle.write_text(content + "\n" + marker + "\n" + statement + "\n", encoding="utf-8")


def proto_fields(data):
    """Read protobuf wire fields; no generated code or external runtime required."""
    position = 0
    def varint():
        nonlocal position
        value = 0
        for shift in range(0, 70, 7):
            if position >= len(data):
                raise ValueError("Truncated Android bundle manifest.")
            byte = data[position]
            position += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError("Invalid protobuf varint.")
    result = {}
    while position < len(data):
        tag = varint()
        field, wire = tag >> 3, tag & 7
        if not field:
            raise ValueError("Invalid protobuf field.")
        if wire == 0:
            value = varint()
        elif wire in (1, 2, 5):
            size = varint() if wire == 2 else (8 if wire == 1 else 4)
            if position + size > len(data):
                raise ValueError("Truncated Android bundle manifest field.")
            value = data[position:position + size]
            position += size
        else:
            raise ValueError("Unsupported protobuf wire type.")
        result.setdefault(field, []).append(value)
    return result


def bundle_element(node):
    # AAPT2 Resources.proto: XmlNode.element=1; XmlElement name=3, attribute=4, child=5.
    # https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/tools/aapt2/Resources.proto
    fields = proto_fields(node)
    if 1 not in fields:
        return None
    element = proto_fields(fields[1][0])
    attributes = {}
    for raw in element.get(4, []):
        attr = proto_fields(raw)
        namespace = attr.get(1, [b""])[0].decode()
        name = attr.get(2, [b""])[0].decode()
        value = attr.get(3, [b""])[0].decode()
        # Compiled string can be retained when raw value is omitted by the resource compiler.
        if not value and 6 in attr:
            item = proto_fields(attr[6][0])
            for string_field in (2, 3):
                if string_field in item:
                    value = proto_fields(item[string_field][0]).get(1, [b""])[0].decode()
        attributes[(namespace, name)] = value
    return element.get(3, [b""])[0].decode(), attributes, element.get(5, [])


def verify_android(artifact, values, project):
    package, label = values["ANDROID_APPLICATION_ID"], values["APP_NAME"]
    if artifact.suffix == ".apk":
        sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
        candidates = list(Path(sdk).glob("build-tools/*/aapt")) if sdk else []
        if not candidates:
            raise ValueError("Android SDK aapt is required to verify the APK identity.")
        aapt = max(candidates, key=lambda p: tuple(int(n) for n in re.findall(r"\d+", p.parent.name)))
        output = run([aapt, "dump", "badging", artifact], project, capture_output=True, text=True).stdout
        match_package = re.search(r"^package: name='([^']*)'", output, re.M)
        match_label = re.search(r"^application-label:'([^']*)'", output, re.M)
        if not match_package or not match_label or (match_package[1], match_label[1]) != (package, label):
            raise ValueError("APK application ID/name does not match Jenkins parameters.")
        launcher_labels = re.findall(r"^launchable-activity: name='[^']*' label='([^']*)'", output, re.M)
        if any(value != label for value in launcher_labels):
            raise ValueError("APK launcher name does not match Jenkins parameters.")
    else:
        with zipfile.ZipFile(artifact) as archive:
            info = archive.getinfo("base/manifest/AndroidManifest.xml")
            if info.file_size > 16 * 1024 * 1024:
                raise ValueError("Android bundle manifest unexpectedly large.")
            manifest = bundle_element(archive.read(info))
        if not manifest or manifest[0] != "manifest" or manifest[1].get(("", "package")) != package:
            raise ValueError("AAB application ID does not match Jenkins parameters.")
        applications = [item for node in manifest[2] if (item := bundle_element(node)) and item[0] == "application"]
        if len(applications) != 1 or applications[0][1].get((ANDROID_NS, "label")) != label:
            raise ValueError("AAB application name does not match Jenkins parameters.")
        for raw_component in applications[0][2]:
            component = bundle_element(raw_component)
            if not component or component[0] not in ("activity", "activity-alias"):
                continue
            launcher = False
            for raw_intent in component[2]:
                intent = bundle_element(raw_intent)
                if intent and intent[0] == "intent-filter":
                    for raw_category in intent[2]:
                        category = bundle_element(raw_category)
                        if category and category[0] == "category" and category[1].get((ANDROID_NS, "name")) == "android.intent.category.LAUNCHER":
                            launcher = True
            if launcher and component[1].get((ANDROID_NS, "label"), label) != label:
                raise ValueError("AAB launcher name does not match Jenkins parameters.")


def validate_android_signing(values, environ=None):
    if values["BUILD_MODE"] != "release":
        return
    env = os.environ if environ is None else environ
    selection = env.get("ANDROID_RELEASE_SIGNING", "")
    if selection not in ("jenkins", "project"):
        raise ValueError("Android release builds require ANDROID_RELEASE_SIGNING=jenkins or project explicitly.")
    if selection == "jenkins":
        keys = ("ANDROID_KEYSTORE_FILE", "ANDROID_STORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD")
        if not all(env.get(key) for key in keys):
            raise ValueError("All four Android signing credential bindings are required.")
        keyfile = Path(env["ANDROID_KEYSTORE_FILE"])
        if not keyfile.is_absolute() or not keyfile.is_file():
            raise ValueError("Android signing keystore binding must reference an existing absolute file.")


def build(project, platform, values):
    if platform == "android":
        validate_android_signing(values)
    relative = f"build/ci/{values['ENVIRONMENT']}/{values['BUILD_MODE']}/{platform}"
    clean(project, relative)
    output = inside(project, relative)
    output.mkdir(parents=True)
    public_child = os.environ.copy()
    for credential in ("IOS_P12_FILE", "IOS_P12_PASSWORD", "IOS_PROFILE_FILE", "ANDROID_KEYSTORE_FILE", "ANDROID_STORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD"):
        public_child.pop(credential, None)
    run(["flutter", "pub", "get"], project, env=public_child)
    if platform == "ios":
        run([sys.executable, CENTRAL / "scripts/build-ios.py", "--project", project], project)
        expected = output / ("app.zip" if values["BUILD_MODE"] == "debug" else "app.ipa")
        if not expected.is_file() or not expected.stat().st_size or not (output / "SUCCESS").is_file():
            raise ValueError("iOS runner did not produce a verified artifact.")
        return
    defines = [f"--dart-define={key}={values[key]}" for key in ("ENVIRONMENT", "APP_NAME", "API_BASE_URL")]
    if platform == "web":
        prepare_web(project, values["APP_NAME"])
        clean(project, "build/web")
        run(["flutter", "build", "web", f"--{values['BUILD_MODE']}", "--no-pub", *defines], project)
        source = inside(project, "build/web")
        if not (source / "main.dart.js").is_file() or not (source / "index.html").is_file():
            raise ValueError("Flutter did not produce a complete web artifact.")
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("name") != values["APP_NAME"] or manifest.get("short_name") != values["APP_NAME"]:
            raise ValueError("Built web application name differs from Jenkins parameters.")
        shutil.make_archive(str(output / "app"), "zip", source)
    else:
        prepare_android(project, values["APP_NAME"])
        clean(project, "build/app/outputs")
        mode = values["BUILD_MODE"]
        target = "apk" if mode == "debug" else "appbundle"
        flavor = ["--flavor", values["ANDROID_FLAVOR"]] if values["ANDROID_FLAVOR"] else []
        run(["flutter", "build", target, f"--{mode}", "--no-pub", *flavor, *defines], project)
        pattern = "build/app/outputs/flutter-apk/*.apk" if mode == "debug" else "build/app/outputs/bundle/**/*.aab"
        candidates = list(project.glob(pattern))
        if len(candidates) != 1 or not candidates[0].stat().st_size:
            raise ValueError("Expected exactly one newly built Android artifact.")
        artifact = candidates[0]
        if not artifact.resolve().is_relative_to(project):
            raise ValueError("Android artifact escapes disposable checkout.")
        verify_android(artifact, values, project)
        shutil.copy2(artifact, output / ("app.apk" if mode == "debug" else "app.aab"))
    (output / "SUCCESS").write_text(f"{values['ENVIRONMENT']} {values['BUILD_MODE']} {platform}\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "quality", "build"))
    parser.add_argument("--project")
    parser.add_argument("--platform", choices=("web", "android", "ios"))
    args = parser.parse_args(argv)
    values = settings()
    if args.action == "validate":
        print("Central build parameters are valid.")
        return
    if not args.project or (args.action == "build" and not args.platform):
        parser.error("--project is required, and build also requires --platform")
    project = project_path(args.project)
    if args.action == "quality":
        quality(project)
    else:
        build(project, args.platform, values)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, ET.ParseError, zipfile.BadZipFile, KeyError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
