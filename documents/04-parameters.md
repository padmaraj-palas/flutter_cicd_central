# Job Parameters Reference

All 41 parameters, their allowed values, and validation rules. These are stored as
Jenkins job parameters and used for both manual and SCM-triggered builds.

> **Parameters are public compiled values.** `APP_NAME`, `API_BASE_URL`, the application
> IDs — all end up inside the built artifact. **Never put secrets in parameters.** Secrets
> live in Jenkins credentials; parameters hold only the *credential ID* pointing at them.

---

## Quick start — minimum viable job

For a first unsigned build, only these need real values:

| Parameter | Example |
| --- | --- |
| `APP_REPOSITORY_URL` | `https://github.com/you/my_app` |
| `APP_BRANCH` | `main` |
| `PLATFORM` | `ios` |
| `BUILD_MODE` | `debug` |
| `APP_NAME` | `My App Staging` |
| `ANDROID_APPLICATION_ID` | `com.example.myapp` |
| `IOS_BUNDLE_ID` | `com.example.myapp` |
| `API_BASE_URL` | `https://staging-api.example.com` |

Everything else can keep its default. **Both platform IDs are required even for a
single-platform build** — the shared validator checks both regardless of `PLATFORM`.

---

## 1. Application source

| Parameter | Type | Description |
| --- | --- | --- |
| `APP_REPOSITORY_URL` | String | Your Flutter app's Git URL. HTTPS (`https://host/path`), SSH (`ssh://user@host/path`), or SCP-style (`user@host:path`). No query string, fragment, embedded credentials, or whitespace. |
| `APP_BRANCH` | String | One literal branch, e.g. `main` or `staging`. May be `refs/heads/<branch>`. **Tags and PR refs are rejected** — the app must track a branch. No wildcards. |
| `APP_CREDENTIALS_ID` | String | Jenkins credential **ID** for private repos. Empty for public. Matches `[A-Za-z0-9_.-]*`. |

---

## 2. Build configuration

| Parameter | Type | Allowed values | Description |
| --- | --- | --- | --- |
| `ENVIRONMENT` | Choice | `testing`, `staging`, `production` | A build label, passed as a Dart define and used in the artifact path. **Does not select a native flavor.** |
| `BUILD_MODE` | Choice | `debug`, `release` | `debug` needs no signing. `release` requires signing configuration. |
| `PLATFORM` | Choice | `android`, `web`, `ios`, `all` | Which platforms to build. `all` means all three. |

### Artifact matrix

Output path: `app/build/ci/<ENVIRONMENT>/<BUILD_MODE>/<platform>/`

| PLATFORM | BUILD_MODE | Artifact | Requires |
| --- | --- | --- | --- |
| `android` | `debug` | `app.apk` | — |
| `android` | `release` | `app.aab` | Android signing |
| `web` | either | `app.zip` | — |
| `ios` | `debug` | `app.zip` (unsigned simulator build) | — |
| `ios` | `release` | `app.ipa` | Apple signing |

---

## 3. Application identity

These values are written into the **disposable checkout** only. Your app repository is
never modified.

| Parameter | Type | Rule | Description |
| --- | --- | --- | --- |
| `APP_NAME` | String | `[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}` | Android launcher label, iOS display name, Web title and PWA manifest name. 1–80 chars, starts with a letter or digit. |
| `API_BASE_URL` | String | Valid `http`/`https` URL | Passed as a Dart define. No credentials, query, fragment, whitespace, or any of `` ` `` `$` `\` `"` `'` `<` `>`. |
| `ANDROID_APPLICATION_ID` | String | `[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+` | Exact Android install ID. Underscores allowed; each segment starts with a letter. |
| `IOS_BUNDLE_ID` | String | `[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+` | Exact iOS bundle ID. **Underscores are NOT allowed** — hyphens only. |
| `ANDROID_FLAVOR` | String | `[A-Za-z][A-Za-z0-9_-]*` or empty | Existing product flavor. Empty for unflavored apps. Does not create flavors. |
| `IOS_SCHEME` | String | `[A-Za-z][A-Za-z0-9_-]*` | An existing **shared** Xcode scheme, normally `Runner`. Must not be empty. |

> **`APP_NAME` only affects what CI can control**: the Android label, iOS display name,
> and Web metadata. A hardcoded title inside your Dart source is unchanged unless the
> app reads the `APP_NAME` Dart define. CI will not rewrite arbitrary application logic.

> Note the asymmetry: `com.example.my_app` is a valid `ANDROID_APPLICATION_ID` but an
> **invalid** `IOS_BUNDLE_ID`. Use `com.example.myApp` or `com.example.my-app` for iOS.

---

## 4. Infrastructure

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `LINUX_AGENT_LABEL` | String | `built-in` | Node label for Android/Web. `[A-Za-z0-9][A-Za-z0-9_.-]{0,79}` |
| `MACOS_AGENT_LABEL` | String | `flutter-macos` | Node label for iOS. **Cannot be `built-in` or `master`** when `PLATFORM` is `ios` or `all` — iOS needs a dedicated native agent. |
| `FLUTTER_IMAGE` | String | `flutter-ci:1.0` | Docker image for Linux builds. Tag or `@sha256:` digest. |

---

## 5. Android signing

| Parameter | Type | Allowed values | Description |
| --- | --- | --- | --- |
| `ANDROID_RELEASE_SIGNING` | Choice | `jenkins`, `project` | `jenkins`: CI supplies a keystore from credentials. `project`: reuse the app's own existing signing config. |
| `ANDROID_KEYSTORE_CREDENTIAL_ID` | String | credential ID | **Secret file** credential holding the keystore. |
| `ANDROID_STORE_PASSWORD_CREDENTIAL_ID` | String | credential ID | **Secret text** — keystore password. |
| `ANDROID_KEY_ALIAS_CREDENTIAL_ID` | String | credential ID | **Secret text** — key alias. |
| `ANDROID_KEY_PASSWORD_CREDENTIAL_ID` | String | credential ID | **Secret text** — key password. |

**Rules**

- `ANDROID_RELEASE_SIGNING=project` → all four credential IDs **must be empty**.
- `PLATFORM` in (`android`,`all`) + `BUILD_MODE=release` + `jenkins` → **all four required**.
- `project` signing may still use a debug key; it does not guarantee a store-ready build.

---

## 6. iOS signing

| Parameter | Type | Allowed values | Description |
| --- | --- | --- | --- |
| `IOS_RELEASE_SIGNING` | Choice | `jenkins`, `existing-keychain` | `jenkins`: CI builds an ephemeral keychain from credentials. `existing-keychain`: the agent already has usable signing assets. |
| `IOS_TEAM_ID` | String | exactly `[A-Z0-9]{10}` | Apple Developer Team ID. Required for iOS release. |
| `IOS_EXPORT_METHOD` | Choice | `app-store-connect`, `release-testing`, `debugging`, `enterprise` | Xcode export method. |
| `IOS_SIGNING_STYLE` | Choice | `manual`, `automatic` | Manual requires an explicit profile. |
| `IOS_PROFILE_NAME` | String | literal name | Exact provisioning profile **Name**. No shell metacharacters (`"` `'` `\` `$` `` ` ``). |
| `IOS_CODE_SIGN_IDENTITY` | Choice | `Apple Distribution`, `Apple Development` | Signing identity type. |
| `IOS_P12_CREDENTIAL_ID` | String | credential ID | **Secret file** — signing certificate `.p12`. |
| `IOS_PASSWORD_CREDENTIAL_ID` | String | credential ID | **Secret text** — the `.p12` password. |
| `IOS_PROFILE_CREDENTIAL_ID` | String | credential ID | **Secret file** — `.mobileprovision`. |

**Rules**

- `IOS_RELEASE_SIGNING=existing-keychain` → the three credential IDs **must be empty**.
- `PLATFORM` in (`ios`,`all`) + `BUILD_MODE=release`:
  - `IOS_TEAM_ID` required
  - `IOS_SIGNING_STYLE=manual` → `IOS_PROFILE_NAME` required
  - `IOS_RELEASE_SIGNING=jenkins` → all three credential IDs required **and**
    `IOS_SIGNING_STYLE` must be `manual`
- iOS **debug** produces an unsigned simulator archive and needs none of this.

The pipeline validates that the provisioning profile's team and app ID match
`IOS_TEAM_ID` and `IOS_BUNDLE_ID`, verifies the exported IPA, and cleans up temporary
signing material.

---

## 7. Upload destinations

All default to `none`. Artifacts are always archived in Jenkins **before** any upload, so
a failed upload still leaves a downloadable artifact (the build is marked failed).

| Parameter | Type | Allowed values |
| --- | --- | --- |
| `ANDROID_UPLOAD_DESTINATION` | Choice | `none`, `firebase`, `google` |
| `IOS_UPLOAD_DESTINATION` | Choice | `none`, `firebase`, `appstore` |
| `WEB_UPLOAD_DESTINATION` | Choice | `none` (Web is archive-only) |

### 7.1 Firebase App Distribution

| Parameter | Type | Rule | Description |
| --- | --- | --- | --- |
| `FIREBASE_CREDENTIALS_ID` | String | credential ID | **Secret file** — Firebase service-account JSON. |
| `FIREBASE_ANDROID_APP_ID` | String | `1:<digits>:android:<alnum>` | Firebase Android app ID. |
| `FIREBASE_IOS_APP_ID` | String | `1:<digits>:ios:<alnum>` | Firebase iOS app ID. |
| `FIREBASE_GROUPS` | String | `alias1,alias2` | Comma-separated tester group aliases. **No spaces.** |

Requires `FIREBASE_CREDENTIALS_ID` plus the matching platform app ID.
iOS via Firebase requires `IOS_EXPORT_METHOD` of `release-testing`, `debugging` or
`enterprise`, and the Firebase CLI on the agent's service `PATH`.

### 7.2 Google Play

| Parameter | Type | Allowed values | Description |
| --- | --- | --- | --- |
| `GOOGLE_PLAY_CREDENTIALS_ID` | String | credential ID | **Secret file** — Play service-account JSON. |
| `GOOGLE_PLAY_TRACK` | Choice | `internal`, `alpha`, `beta`, `production` | Release track. |
| `GOOGLE_PLAY_RELEASE_STATUS` | Choice | `draft`, `completed` | Release status. |

**Requires an Android release AAB** — `BUILD_MODE=release`. Debug APKs are rejected.

### 7.3 App Store Connect / TestFlight

| Parameter | Type | Description |
| --- | --- | --- |
| `APPSTORE_API_KEY_CREDENTIALS_ID` | String | **Secret file** — App Store Connect API key JSON. |

Requires a **signed release IPA** and `IOS_EXPORT_METHOD=app-store-connect`. Simulator
builds cannot be uploaded. Uploads to TestFlight **without** submitting for App Review
or releasing publicly.

### 7.4 Release notes

| Parameter | Type | Rule |
| --- | --- | --- |
| `UPLOAD_RELEASE_NOTES` | String | Max **500 characters**, single line |

---

## 8. Cross-parameter rules — quick checklist

| Condition | Requirement |
| --- | --- |
| Always | Both `ANDROID_APPLICATION_ID` **and** `IOS_BUNDLE_ID` valid |
| Always | `IOS_SCHEME` non-empty |
| `PLATFORM` = `ios`/`all` | `MACOS_AGENT_LABEL` set, and not `built-in`/`master` |
| Android release + `jenkins` signing | All 4 Android credential IDs |
| Android release + `project` signing | All 4 Android credential IDs **empty** |
| iOS release | `IOS_TEAM_ID` |
| iOS release + manual style | `IOS_PROFILE_NAME` |
| iOS release + `jenkins` signing | All 3 iOS credential IDs **and** `manual` style |
| iOS + `existing-keychain` | All 3 iOS credential IDs **empty** |
| Any Firebase upload | `FIREBASE_CREDENTIALS_ID` + platform app ID |
| Google Play upload | `GOOGLE_PLAY_CREDENTIALS_ID` + Android **release** |
| App Store upload | `APPSTORE_API_KEY_CREDENTIALS_ID` + `app-store-connect` export |

Validate before building:

```bash
python3 automation/scripts/setup.py validate --config /path/to/answers.json
```

---

## 9. Creating Jenkins credentials

**Manage Jenkins → Credentials → System → Global credentials → Add Credentials**

| Credential purpose | Jenkins kind |
| --- | --- |
| Git repository access | Username/password, or SSH key |
| Android keystore | **Secret file** |
| Android passwords / alias | **Secret text** |
| iOS `.p12` | **Secret file** |
| iOS `.p12` password | **Secret text** |
| iOS `.mobileprovision` | **Secret file** |
| Firebase / Google Play / App Store JSON | **Secret file** |

Put only the **ID** into the job parameter.

---

## 10. `answers.json` template

Used by the automation helper. Keep it in a protected directory **outside** both
repositories (e.g. `~/ci/setup/`, mode `700`).

```json
{
  "schema_version": 1,
  "confirmed": true,
  "project_id": "myapp",
  "job_name": "MyApp-Staging-iOS",
  "jenkins": {
    "url": "http://127.0.0.1:8080",
    "poll_schedule": "H/5 * * * *"
  },
  "ci": {
    "repository_url": "https://github.com/your-org/flutter-cicd-central.git",
    "ref": "main",
    "script_path": "Jenkinsfile",
    "credentials_id": ""
  },
  "parameters": {
    "APP_REPOSITORY_URL": "https://github.com/your-org/your-app",
    "APP_BRANCH": "main",
    "APP_CREDENTIALS_ID": "",
    "ENVIRONMENT": "staging",
    "BUILD_MODE": "debug",
    "PLATFORM": "ios",
    "APP_NAME": "My App Staging",
    "API_BASE_URL": "https://staging-api.example.com",
    "ANDROID_APPLICATION_ID": "com.example.myapp",
    "IOS_BUNDLE_ID": "com.example.myapp",
    "ANDROID_FLAVOR": "",
    "IOS_SCHEME": "Runner",
    "LINUX_AGENT_LABEL": "built-in",
    "MACOS_AGENT_LABEL": "flutter-macos",
    "FLUTTER_IMAGE": "flutter-ci:1.0",
    "ANDROID_RELEASE_SIGNING": "project",
    "ANDROID_KEYSTORE_CREDENTIAL_ID": "",
    "ANDROID_STORE_PASSWORD_CREDENTIAL_ID": "",
    "ANDROID_KEY_ALIAS_CREDENTIAL_ID": "",
    "ANDROID_KEY_PASSWORD_CREDENTIAL_ID": "",
    "IOS_RELEASE_SIGNING": "existing-keychain",
    "IOS_TEAM_ID": "",
    "IOS_EXPORT_METHOD": "release-testing",
    "IOS_SIGNING_STYLE": "manual",
    "IOS_PROFILE_NAME": "",
    "IOS_CODE_SIGN_IDENTITY": "Apple Distribution",
    "IOS_P12_CREDENTIAL_ID": "",
    "IOS_PASSWORD_CREDENTIAL_ID": "",
    "IOS_PROFILE_CREDENTIAL_ID": "",
    "ANDROID_UPLOAD_DESTINATION": "none",
    "IOS_UPLOAD_DESTINATION": "none",
    "WEB_UPLOAD_DESTINATION": "none",
    "FIREBASE_ANDROID_APP_ID": "",
    "FIREBASE_IOS_APP_ID": "",
    "FIREBASE_GROUPS": "",
    "FIREBASE_CREDENTIALS_ID": "",
    "GOOGLE_PLAY_CREDENTIALS_ID": "",
    "APPSTORE_API_KEY_CREDENTIALS_ID": "",
    "UPLOAD_RELEASE_NOTES": "",
    "GOOGLE_PLAY_TRACK": "internal",
    "GOOGLE_PLAY_RELEASE_STATUS": "draft"
  }
}
```

**File-level rules**

| Field | Rule |
| --- | --- |
| `schema_version` | Must be integer `1` |
| `confirmed` | Must be `true` — validation fails while `false` |
| `project_id`, `job_name` | `[A-Za-z][A-Za-z0-9_.-]{0,79}` — start with a letter, **no spaces** |
| `jenkins.poll_schedule` | Five-field Jenkins cron, or `""` to disable polling |
| `ci.ref` | Branch, or `refs/tags/<tag>`. Pin to a tag for reproducibility. |
| `ci.script_path` | Normally `Jenkinsfile` |
