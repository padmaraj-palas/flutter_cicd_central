"""Shared Jenkins upload configuration; missing upload fields retain build-only jobs."""
import re

CHOICES = {
    "ANDROID_UPLOAD_DESTINATION": ("none", "firebase", "google"),
    "IOS_UPLOAD_DESTINATION": ("none", "firebase", "appstore"),
    "WEB_UPLOAD_DESTINATION": ("none",),
    "GOOGLE_PLAY_TRACK": ("internal", "alpha", "beta", "production"),
    "GOOGLE_PLAY_RELEASE_STATUS": ("draft", "completed"),
}
CREDENTIALS = ("FIREBASE_CREDENTIALS_ID", "GOOGLE_PLAY_CREDENTIALS_ID", "APPSTORE_API_KEY_CREDENTIALS_ID")
DEFAULTS = {key: choices[0] for key, choices in CHOICES.items()}
DEFAULTS.update(dict.fromkeys((*CREDENTIALS, "FIREBASE_ANDROID_APP_ID", "FIREBASE_IOS_APP_ID", "FIREBASE_GROUPS", "UPLOAD_RELEASE_NOTES"), ""))


def validate(values):
    result = {**DEFAULTS, **values}
    for key in DEFAULTS:
        value = result[key]
        if not isinstance(value, str) or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError(f"{key} must be a trimmed single-line string.")
        if key in CHOICES and value not in CHOICES[key]:
            raise ValueError(f"{key} must be one of: {', '.join(CHOICES[key])}.")
    for key in CREDENTIALS:
        if result[key] and not re.fullmatch(r"[A-Za-z0-9_.-]+", result[key]):
            raise ValueError(f"{key} must be a Jenkins credential ID, not a credential value.")
    for platform in ("ANDROID", "IOS"):
        key = f"FIREBASE_{platform}_APP_ID"
        if result[key] and not re.fullmatch(r"1:[0-9]+:" + platform.lower() + r":[A-Za-z0-9]+", result[key]):
            raise ValueError(f"{key} must be a Firebase {platform} app ID.")
    if result["FIREBASE_GROUPS"] and not re.fullmatch(r"[A-Za-z0-9_-]+(?:,[A-Za-z0-9_-]+)*", result["FIREBASE_GROUPS"]):
        raise ValueError("FIREBASE_GROUPS must contain comma-separated group aliases without spaces.")
    if len(result["UPLOAD_RELEASE_NOTES"]) > 500:
        raise ValueError("UPLOAD_RELEASE_NOTES must be at most 500 characters.")
    selected = result.get("PLATFORM", "")
    if selected not in ("android", "ios", "web", "all"):
        raise ValueError("PLATFORM must be android, ios, web or all.")
    def require(key):
        if not result.get(key):
            raise ValueError(f"{key} is required for the selected upload destination.")
    for platform in ("android", "ios"):
        if selected not in (platform, "all"):
            continue
        destination = result[f"{platform.upper()}_UPLOAD_DESTINATION"]
        if destination == "none":
            continue
        if result.get("BUILD_MODE") not in ("debug", "release"):
            raise ValueError("Uploads require BUILD_MODE=debug or release.")
        identity = "ANDROID_APPLICATION_ID" if platform == "android" else "IOS_BUNDLE_ID"
        pattern = r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+" if platform == "android" else r"[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+"
        if not re.fullmatch(pattern, result.get(identity, "")):
            raise ValueError(f"{identity} must be a valid native app ID for upload.")
        if destination == "firebase":
            require("FIREBASE_CREDENTIALS_ID")
            require(f"FIREBASE_{platform.upper()}_APP_ID")
        if platform == "android" and destination == "google":
            require("GOOGLE_PLAY_CREDENTIALS_ID")
            if result.get("BUILD_MODE") != "release":
                raise ValueError("Google Play upload requires an Android release AAB.")
        if platform == "ios":
            if result.get("BUILD_MODE") != "release":
                raise ValueError("iOS uploads require a signed release IPA; simulator builds cannot be uploaded.")
            method = result.get("IOS_EXPORT_METHOD")
            if destination == "appstore":
                require("APPSTORE_API_KEY_CREDENTIALS_ID")
                if method != "app-store-connect":
                    raise ValueError("App Store Connect upload requires IOS_EXPORT_METHOD=app-store-connect.")
            elif method not in ("release-testing", "debugging", "enterprise"):
                raise ValueError("Firebase iOS upload requires release-testing, debugging or enterprise export.")
    return result
