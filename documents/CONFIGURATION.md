# Job configuration, signing and uploads

Use this guide after host setup for [Windows/WSL](SETUP_WINDOWS_WSL.md), [Linux](SETUP_LINUX.md) or [macOS](SETUP_MACOS.md). It is the single reference for regular Jenkins Pipeline jobs, their 41 public parameters, automated job management, signing and automatic uploads. [Operations](OPERATIONS.md) covers troubleshooting and validation evidence.

- [Create or copy a job](#create-job)
- [Configure a job with answers and helpers](#automation)
- [Create credentials](#credentials)
- [Parameter rules and defaults](#parameters)
- [App source and build selection](#source)
- [App identity and public configuration](#identity)
- [Build infrastructure](#infrastructure)
- [Android release signing](#android-signing)
- [iOS release signing](#ios-signing)
- [Upload parameters](#uploads)
- [Firebase App Distribution](#firebase)
- [Google Play](#google-play)
- [App Store Connect / TestFlight](#appstore)
- [Setup-only fields](#setup-fields)
- [Host inputs and runtime bindings](#host-inputs)
- [Example jobs and artifacts](#examples)

<a id="create-job"></a>
## Create or copy a job

Publish the contents of this central repository, including hidden files, to the root of a reachable GitHub, GitLab or other Git repository. Keep `Jenkinsfile` at its root and pin jobs to a reviewed central tag or commit. All CI scripts, Ruby bundles, signing helpers and setup files stay here. There is no app-repository CI installation, commit or push step.

1. In Jenkins choose **New Item > Pipeline** and a unique name. Use a regular Pipeline job, with one saved configuration per job.
2. Open **General > This project is parameterized**. Add the fields in the parameter tables below. For a Choice Parameter, save **one chosen value** in Choices. For a String Parameter, save the job's value in Default Value. The pipeline does not overwrite these settings with its own parameter defaults.
3. Under **Pipeline > Pipeline script from SCM > Git**, enter the **central repository URL**, its credential and reviewed version, such as `refs/tags/your-reviewed-fixed-release` (replace this placeholder with a published fixed revision). Set **Script Path** to `Jenkinsfile`.
4. Set the separate **app** checkout through `APP_REPOSITORY_URL`, `APP_BRANCH` and `APP_CREDENTIALS_ID`.
5. Enable **Build Triggers > Poll SCM**, for example `H/5 * * * *`, or configure the provider's Jenkins webhook integration for the **app repository** and a reachable Jenkins endpoint. Entering a repository URL does not install a webhook. Polling works without provider-specific webhook setup.
6. Save and run once. The first successful app checkout establishes polling of its configured branch. If a build fails before checkout, fix it and run again. Inspect the artifacts and actual app identity.

Use **New Item > Copy from** for another environment/platform/app. Change its saved repository, branch, environment, mode, names, IDs, signing and upload settings as applicable, then run the copy once to establish its own checkout. When migrating from the older per-project CI package, create a fresh central job because its SCM and parameter contract differ.

SCM-triggered builds use saved job values, including upload destinations. Each run uses the same app commit and central tooling revision across Linux and Mac. Disposable checkouts are recreated; archived artifacts remain available. Choose `none` for uploads while verifying build-only infrastructure.

Official references: [Pipeline SCM polling](https://plugins.jenkins.io/workflow-scm-step/), [Jenkins parameters](https://www.jenkins.io/doc/book/pipeline/syntax/#parameters), [copying jobs](https://www.jenkins.io/doc/book/using/working-with-projects/).

<a id="automation"></a>
## Configure a job with answers and helpers

The authoritative complete template is [automation/answers.example.json](../automation/answers.example.json). Keep one confirmed answers file per job in a protected directory outside the central and app repositories. Commands below run from this repository root in Bash on Linux, WSL or Mac; Windows Python can run the same helpers with the equivalent local paths.

```bash
mkdir -p ~/ci/setup
chmod 700 ~/ci/setup
cp -n automation/answers.example.json ~/ci/setup/answers.json
chmod 600 ~/ci/setup/answers.json
```

Copy only when creating a new answers file; preserve an existing job's answers. Replace example central/app Git URLs and refs, Jenkins URL, `project_id`, `job_name`, and all applicable parameter values. Confirm the actual public settings and set `confirmed` to `true`; the template deliberately starts `false`. Credential fields hold IDs only. For a first debug job, adjust app URL/branch, platform, name, API URL and both native IDs, then review environment, labels, image and all remaining template choices against your host. Debug Android uses its normal debug signing; debug iOS is an unsigned simulator build.

The historical `refs/tags/v1.0.0` failed validation with `CI_PLATFORM: parameter not set`; do not use it for a new setup. Replace any older template ref with a reviewed published revision containing the fixes. See [validation history](OPERATIONS.md).

Every original build/signing key must remain present, even if its value is explicitly empty or the selected platform does not use it. Only upload fields have backward-compatible omission defaults. All supplied choices must be valid. Unknown or duplicate JSON keys are rejected. See [setup-only fields](#setup-fields) and the parameter tables for validation rules.

Validate and render an inspectable job definition without contacting Jenkins:

```bash
python3 automation/scripts/setup.py validate --config ~/ci/setup/answers.json
python3 automation/scripts/setup.py render-job --config ~/ci/setup/answers.json --output ~/ci/setup/job.xml
```

`render-job` creates a new XML file with restrictive permissions and refuses to overwrite an existing file. Choose a new output filename when rendering again. Inspect its central SCM, 41 saved parameters and polling configuration; rendered jobs retain the latest 20 builds and their artifacts.

For an existing controller, create an API token at **your username > Security > API Token**. Supply it through the protected process environment; do not store the token in answers or command history. This Bash example reads it without echoing:

```bash
export JENKINS_USER=admin  # replace with the actual Jenkins user
read -r -s JENKINS_API_TOKEN
export JENKINS_API_TOKEN
python3 automation/scripts/setup.py ensure-job --config ~/ci/setup/answers.json
python3 automation/scripts/setup.py build --config ~/ci/setup/answers.json
```

`ensure-job` creates a missing job or updates a Pipeline bearing the exact ownership description `Managed by flutter-cicd-central; project_id=<project_id>`. It refuses unrelated jobs. Before an update it saves the previous XML beside answers; use `--backup-directory /protected/existing-directory` to select another existing backup directory. Reconcile Jenkins UI edits into answers first: `ensure-job` reapplies the confirmed answers. `build` also verifies ownership, supplies no parameter overrides, and queues the currently saved job settings.

Track the returned queue ID and then its assigned build number. Replace `123` and `7` with the returned identifiers:

```bash
python3 automation/scripts/setup.py status --config ~/ci/setup/answers.json --queue-id 123
python3 automation/scripts/setup.py status --config ~/ci/setup/answers.json --build-number 7
python3 automation/scripts/setup.py status --config ~/ci/setup/answers.json
unset JENKINS_API_TOKEN
```

Queue status includes cancellation, waiting reason and assigned executable; build status includes result, running state, URL and artifacts. Plain `status` reports the job's latest build; use the exact identifiers to follow your own request when others can queue builds. Download and verify the outputs after success.

For a **new empty Jenkins home**, use the fresh-bootstrap procedure for [Windows/WSL](SETUP_WINDOWS_WSL.md#fresh-bootstrap) or [Linux](SETUP_LINUX.md#fresh-bootstrap), after host prerequisites and image preparation. Do not first start the manual wizard for that bootstrap path. An existing home always uses existing-controller management; never add the fresh marker/init hook to it.

For an iOS job, the optional Mac-node helper takes the same answers and separate host inputs. Run on the Mac with protected `JENKINS_USER`/`JENKINS_API_TOKEN` bindings:

```bash
python3 automation/scripts/macos_agent.py --config ~/ci/setup/answers.json \
  --agent-name flutter-mac-01 --remote-fs /Users/ci/jenkins-agent \
  --secret-file /Users/ci/.config/flutter-ci/agent.secret
```

Use your actual CI user's paths and an unused secret-file path outside repositories and the agent workspace. The helper creates or verifies an owned, exclusive, one-executor inbound WebSocket node with the saved Mac label; it refuses mismatching existing nodes and does not print the inbound secret. It refuses to overwrite an existing secret file. Start the agent with the stable `host/macos` launch scripts using the [Mac setup instructions](SETUP_MACOS.md#mac-agent). Record host access, node name and filesystem paths in the local setup report; they are not app parameters.

### Add uploads to an existing job

Update Pipeline SCM to a reviewed central revision containing upload support. Add the upload fields manually, or update the protected answers file, reconcile UI changes, validate/render, and run `ensure-job` against the existing controller. Older answers normalize missing destinations to `none`, Play track to `internal`, status to `draft`, and upload strings to empty. No bootstrap or app changes are needed. Create the selected service credentials through protected administration and enter only their IDs in answers.

### Mac alternative: install rendered XML while Jenkins is stopped

This local option preserves the former Mac setup route without an API token. Use it only for a **new job** under the actual native controller's `JENKINS_HOME`; use `ensure-job` for existing jobs. Finish running builds and back up Jenkins first. The following assumes the controller LaunchAgent installed by [Mac setup](SETUP_MACOS.md), `~/ci/setup/answers.json` and freshly rendered `~/ci/setup/job.xml`. It refuses an existing destination and restarts the controller even if copying fails:

```bash
export JENKINS_HOME="$HOME/ci/jenkins/jenkins_home"  # actual controller home
python3 - <<'PY'
import json, os, re, shutil, subprocess
from pathlib import Path
answers = Path.home() / "ci/setup/answers.json"
rendered = answers.with_name("job.xml")
name = json.loads(answers.read_text())["job_name"]
assert re.fullmatch(r"[A-Za-z][A-Za-z0-9 ._-]{0,79}", name) and name == name.strip(), "Invalid job name"
home = Path(os.environ["JENKINS_HOME"]).resolve()
assert (home / "config.xml").is_file(), "Check the actual Jenkins home"
jobs = home / "jobs"
assert jobs.is_dir() and not jobs.is_symlink(), "Check the Jenkins jobs directory"
target = jobs / name
assert not target.exists() and not target.is_symlink(), "Job exists: use ensure-job"
assert rendered.is_file(), "Render job.xml first"
service = f"gui/{os.getuid()}"
plist = Path.home() / "Library/LaunchAgents/local.flutter-ci.jenkins.plist"
subprocess.run(["launchctl", "bootout", service + "/local.flutter-ci.jenkins"], check=True)
try:
    target.mkdir()  # exclusive creation; never overwrite an existing job
    shutil.copyfile(rendered, target / "config.xml")
finally:
    subprocess.run(["launchctl", "bootstrap", service, str(plist)], check=True)
PY
```

Open Jenkins after restart, verify the saved job configuration and run it once to establish app polling. A partial directory from a failed copy needs inspection before retrying; do not overwrite it blindly.

<a id="credentials"></a>
## Create credentials

Open **Manage Jenkins > Credentials > System > Global credentials > Add Credentials** (or the credential store scoped to the job). Assign a stable ID and select the kind below. Enter the secret/file only through protected administration; put only its ID in job parameters or answers.

| Purpose | Jenkins kind |
| --- | --- |
| Central/app HTTPS Git access | Username with password; use the Git provider token as password when required |
| Central/app SSH Git access | SSH Username with private key |
| Android keystore | Secret file |
| Android store password, key alias, key password | Three separate Secret text credentials |
| iOS signing certificate/private key `.p12` | Secret file |
| iOS P12 password | Secret text; bound signing requires a nonempty password |
| iOS `.mobileprovision` | Secret file |
| Firebase, Google Play or App Store Connect JSON | Separate Secret file credentials as selected |

Signing credentials prove the build's identity; upload credentials authorize a service operation. They are separate bindings. Public app names, IDs, API URLs and release notes can be compiled into/downloaded with the artifact; they must not contain secrets.

<a id="parameters"></a>
## Parameter rules and defaults

Download [PARAMETERS.csv](PARAMETERS.csv) for all 41 Jenkins job parameters, expected values, defaults, examples, descriptions and conditional requirements. Blank CSV defaults mean an empty string; non-upload parameters have no implicit pipeline default. Examples illustrate individual fields and must be adapted together for the selected job; they are not a ready-to-import configuration. The CSV contains credential IDs only and excludes setup-only fields and runtime secret bindings.

The 41 uppercase names are keys inside the parameters object in [answers.example.json](../automation/answers.example.json). The helper requires every original build/signing key, even when its explicit value is empty or the platform does not use it. Upload fields may be omitted for compatibility: destinations default to none, Google Play track to internal, release status to draft, and upload strings to empty. Every supplied Choice key needs a valid choice even when unused. Examples below are illustrative, not values to copy without confirmation.

All values are case-sensitive. Strings must be single-line without leading/trailing whitespace. Credential IDs accept letters, digits, underscores, dots and hyphens; they are references to credentials, not secrets.

The non-upload values in the example are starting choices, not Jenkinsfile defaults. For the packaged topology they include `LINUX_AGENT_LABEL=built-in`, `MACOS_AGENT_LABEL=flutter-macos` and `FLUTTER_IMAGE=flutter-ci:1.0`; saving a job does not provision those resources.

<a id="source"></a>
## App source and build selection

| Parameter | Type | Possible values / example | Short description |
| --- | --- | --- | --- |
| APP_REPOSITORY_URL | String | HTTPS, ssh://user@host/path, or user@host:path Git URL; e.g. https://gitlab.com/team/app.git | Flutter repository to check out. No embedded passwords/tokens, query, fragment or whitespace. Current URL validation supports simple host/path characters, not arbitrary encoded URLs. |
| APP_BRANCH | String | Literal branch such as main, staging, feature/login or refs/heads/staging | App branch to build and poll. No wildcard, tag ref, pull-request ref or commit-selector mode. Must be a valid supported Git branch name. |
| APP_CREDENTIALS_ID | String | Credential ID such as app-git; empty for access needing no Jenkins credential | Git credentials for the app, separate from central-repository credentials. HTTPS normally uses Username with password/token; SSH uses SSH Username with private key. |
| ENVIRONMENT | Choice | testing, staging, production | Output grouping and Dart define. Does not load an environment file or automatically select a flavor. |
| BUILD_MODE | Choice | debug, release | Flutter build mode. No profile mode is exposed. |
| PLATFORM | Choice | android, web, ios, all | all runs Web, Android and iOS; a native Mac worker is required for ios/all. No comma-separated platform subsets. |

<a id="identity"></a>
## App identity and public configuration

| Parameter | Type | Possible values / example | Short description |
| --- | --- | --- | --- |
| APP_NAME | String | 1-80 ASCII letters/digits, spaces, dots, underscores, hyphens; first character letter/digit. Example: My App Staging | Android launcher label, iOS display name and Web document/PWA name. Also a Dart define. |
| API_BASE_URL | String | Absolute http:// or https:// URL with valid port; e.g. https://api-staging.company.com/v1 | Public Dart define. Setup rejects credentials, whitespace, query/fragment, backticks, dollar signs, backslashes, quotes and angle brackets. |
| ANDROID_APPLICATION_ID | String | Dotted ID with each segment starting with a letter; remaining characters letters/digits/underscore. Example: com.company.app.staging | Exact Android install ID. Central adapter clears application-ID suffixes; namespace/source packages stay unchanged. |
| IOS_BUNDLE_ID | String | Dotted ID with alphanumeric segment starts and remaining letters/digits/hyphens. Example: com.company.app.staging | Exact iOS bundle ID; must match signing profile for device releases. |
| ANDROID_FLAVOR | String | Empty for unflavored apps, otherwise an existing name such as qa or staging; starts with a letter, then letters/digits/underscore/hyphen | Selects an existing native Android flavor. It does not create flavors. The project's actual flavor/AGP rules must also accept the name. |
| IOS_SCHEME | String | Runner, an existing shared scheme such as staging, or empty to use Runner; same simple name characters as above | Selects an existing shared Runner scheme. It does not create schemes. |

APP_NAME, API_BASE_URL and both application IDs are required by common validation even for a single-platform build. No app environment configuration files are used. Existing Dart code must read the defines for API/in-screen title changes; the central system does not rewrite that source.

For example, `com.example.my_app` is valid on Android but invalid as an iOS bundle ID; use an iOS-compatible value such as `com.example.myApp` or `com.example.my-app`. The pipeline passes `ENVIRONMENT`, `APP_NAME` and `API_BASE_URL` using `--dart-define`. Hardcoded Dart API/title values remain unchanged and must be reported as an app compatibility limit.

<a id="infrastructure"></a>
## Build infrastructure

| Parameter | Type | Possible values / example | Short description |
| --- | --- | --- | --- |
| LINUX_AGENT_LABEL | String | One literal label, 1-80 characters, alphanumeric first, then letters/digits/underscore/dot/hyphen; e.g. built-in | Node launching Linux build containers for Web/Android, including the native Mac controller. The controller/Docker workspace mount topology must match; a label alone does not provision a worker. |
| MACOS_AGENT_LABEL | String | Same label format; e.g. flutter-macos. built-in and master are rejected for ios/all | Native Mac worker for iOS. Must be online with Xcode/Flutter and matching tools. |
| FLUTTER_IMAGE | String | Docker image reference, optionally registry/port, tag or sha256 digest; e.g. flutter-ci:1.0 or registry.company.com/mobile/flutter:3.47.0 | Linux build image. No whitespace, command flags or embedded credentials. Use an image already built/pulled on the correct daemon. |

The automation schema requires both labels and an image even when that platform will not execute. Image/node creation and tool installation are host setup, not effects of saving these fields.

<a id="android-signing"></a>
## Android release signing

| Parameter | Type | Possible values / example | Short description |
| --- | --- | --- | --- |
| ANDROID_RELEASE_SIGNING | Choice | jenkins, project | jenkins uses bound credentials; project preserves the app's existing signing configuration. Used for Android release builds. |
| ANDROID_KEYSTORE_CREDENTIAL_ID | String | Secret file credential ID, e.g. android-release-keystore; empty when unused | Keystore file for central release signing. |
| ANDROID_STORE_PASSWORD_CREDENTIAL_ID | String | Secret text credential ID, e.g. android-store-password; empty when unused | Keystore password reference. |
| ANDROID_KEY_ALIAS_CREDENTIAL_ID | String | Secret text credential ID, e.g. android-key-alias; empty when unused | Signing key alias reference. |
| ANDROID_KEY_PASSWORD_CREDENTIAL_ID | String | Secret text credential ID, e.g. android-key-password; empty when unused | Signing key password reference. |

For android/all + release + jenkins, all four IDs must be nonempty and resolve to the stated credential types. In project mode all four central IDs must be empty in setup answers. Project signing may still use a debug key; this mode is not proof of store-ready signing. Debug builds do not bind these release credentials.

<a id="ios-signing"></a>
## iOS release signing

| Parameter | Type | Possible values / example | Short description |
| --- | --- | --- | --- |
| IOS_RELEASE_SIGNING | Choice | jenkins, existing-keychain | jenkins imports bound signing material into an ephemeral keychain; existing-keychain uses already usable Mac credentials. |
| IOS_TEAM_ID | String | Exactly 10 uppercase letters/digits, e.g. ABCDE12345; empty when no iOS release is selected | Apple developer team used to build/export. Use the actual team, not the example. |
| IOS_EXPORT_METHOD | Choice | app-store-connect, release-testing, debugging, enterprise | Xcode export method: App Store Connect artifact, release testing, development/debugging, or enterprise distribution. Does not upload the IPA. Must match the available Apple signing assets. |
| IOS_SIGNING_STYLE | Choice | manual, automatic | Xcode signing style. Bound Jenkins P12/profile mode requires manual; automatic is supported only through existing-keychain mode. |
| IOS_PROFILE_NAME | String | Exact provisioning-profile Name; e.g. My App Staging AdHoc; empty when not required | Required for manual iOS release signing. This is the profile Name, not its filename/UUID/credential ID. No quotes, backslash, dollar sign or backtick. |
| IOS_CODE_SIGN_IDENTITY | Choice | Apple Distribution, Apple Development | Certificate identity category; choose one matching the export/profile. |
| IOS_P12_CREDENTIAL_ID | String | Secret file credential ID, e.g. ios-distribution-p12; empty when unused | P12 containing signing certificate and private key. |
| IOS_PASSWORD_CREDENTIAL_ID | String | Secret text credential ID, e.g. ios-p12-password; empty when unused | P12 password reference. Current bound-signing runner requires a nonempty password. |
| IOS_PROFILE_CREDENTIAL_ID | String | Secret file credential ID, e.g. ios-staging-profile; empty when unused | Provisioning-profile file reference. |

For ios/all + release: Team ID is required; manual style also requires profile Name. With jenkins, all three credential IDs are required and style must be manual. The profile must explicitly match the configured team, bundle ID and Name; wildcard profiles are not accepted by the bound-signing adapter.

With existing-keychain, all three Jenkins signing IDs must be empty, including in setup for non-iOS/debug jobs. The Mac must already have a usable identity/profile. Debug builds create an unsigned simulator ZIP and need no Apple signing assets.

Bound signing creates an ephemeral keychain, validates profile team/app/name, exports and verifies the IPA, and cleans up temporary signing material. Existing shared Runner schemes are supported; custom app targets/extensions need a central adapter. iOS dependencies live in [scripts/ios/Gemfile](../scripts/ios/Gemfile), never in an app Gemfile. Actual Xcode simulator/release builds are required to establish host compilation and signing success.

<a id="uploads"></a>
## Upload parameters

Uploads run after the platform artifact is successfully built, verified and archived. Destinations are independent saved job settings; `PLATFORM=all` uses each platform's setting. Existing jobs with no upload parameters continue to build/archive only. Service preparation is described in the destination sections below.

| Parameter | Type | Possible values / default | Short description |
| --- | --- | --- | --- |
| ANDROID_UPLOAD_DESTINATION | Choice | none, firebase, google; default none | Archive only, Firebase App Distribution, or Google Play. |
| IOS_UPLOAD_DESTINATION | Choice | none, firebase, appstore; default none | Archive only, Firebase App Distribution, or App Store Connect/TestFlight upload. |
| WEB_UPLOAD_DESTINATION | Choice | none | Reserved for future deployment; currently archive only. |
| FIREBASE_ANDROID_APP_ID | String | Empty or 1:1234567890:android:abc123 | Required for selected Android Firebase upload; Firebase app ID, not Android package name. |
| FIREBASE_IOS_APP_ID | String | Empty or 1:1234567890:ios:abc123 | Required for selected iOS Firebase upload; Firebase app ID, not bundle ID. |
| FIREBASE_GROUPS | String | Empty or qa-team,internal-testers | Comma-separated group aliases without spaces; letters, digits, underscores and hyphens. Empty uploads without selecting tester groups. |
| FIREBASE_CREDENTIALS_ID | String | Empty or firebase-distribution | Jenkins Secret file ID holding a Google service-account JSON with Firebase App Distribution access. Required for either selected Firebase destination. |
| GOOGLE_PLAY_CREDENTIALS_ID | String | Empty or google-play-upload | Jenkins Secret file ID holding Google Play service-account JSON. Required for selected google destination. |
| GOOGLE_PLAY_TRACK | Choice | internal, alpha, beta, production; default internal | Google Play track for the uploaded release. |
| GOOGLE_PLAY_RELEASE_STATUS | Choice | draft, completed; default draft | draft retains a draft release; completed requests release on the selected track, subject to Play requirements/review. |
| APPSTORE_API_KEY_CREDENTIALS_ID | String | Empty or appstore-upload | Jenkins Secret file ID holding Fastlane App Store Connect API-key JSON. Required for selected appstore destination. |
| UPLOAD_RELEASE_NOTES | String | Empty by default; up to 500 characters | Optional trimmed single-line release notes; no secrets. |

Android Firebase uses the current output: debug APK or release AAB. Firebase AAB distribution requires Google Play linkage and its prerequisites. Google Play requires BUILD_MODE=release and a correctly signed AAB. iOS uploads require BUILD_MODE=release and a signed IPA: Firebase accepts IOS_EXPORT_METHOD=release-testing, debugging or enterprise; appstore requires app-store-connect. Simulator archives cannot be uploaded. The appstore destination uploads the binary to App Store Connect for TestFlight; it does not submit an App Review request or automatically release the app publicly.

Signing credentials and upload credentials serve separate purposes. Upload credentials are bound only in the upload stage, after artifact archival. An upload failure fails the build while preserving its archived artifact. Selecting an upload destination enables uploads on automatic SCM builds too.

Only selected platforms run their upload stage. All supplied upload values still undergo syntax/choice validation, even for an unused platform. `none` archives without uploading. All Fastlane dependencies stay in the separate central [scripts/upload/Gemfile](../scripts/upload/Gemfile); Firebase, Google Play and App Store Connect all use central Fastlane. Firebase uses the locked `fastlane-plugin-firebase_app_distribution` plugin. No Fastfile, store metadata or Firebase SDK/config files are installed in an app repository. The pipeline prepares dependencies before binding upload credentials.

Service-tool output is suppressed to avoid credential leakage; failures identify the destination and exit code. Check the destination console for permissions, app registration, signing and version uniqueness. Tests of validation or stubs are not proof of a real upload; see [recorded validation](OPERATIONS.md).

<a id="firebase"></a>
## Firebase App Distribution

Set `ANDROID_UPLOAD_DESTINATION=firebase` and/or `IOS_UPLOAD_DESTINATION=firebase` on the selected job. Existing Firebase job settings continue to work after selecting a central revision with this Fastlane implementation.

Register the Android package name/iOS bundle ID in the intended Firebase project and enable App Distribution. Copy the Firebase **App ID** into FIREBASE_ANDROID_APP_ID or FIREBASE_IOS_APP_ID; it is different from the native package/bundle ID. Create tester groups and put their aliases in FIREBASE_GROUPS, for example `qa-team,internal-testers`, or leave it empty to upload without selecting groups. Registering an app is sufficient when only App Distribution is used; no Firebase SDK installation is needed. See the official [Android Fastlane guide](https://firebase.google.com/docs/app-distribution/android/distribute-fastlane) and [iOS Fastlane guide](https://firebase.google.com/docs/app-distribution/ios/distribute-fastlane).

Provide a service-account JSON with Firebase App Distribution permissions as a Jenkins Secret file and set FIREBASE_CREDENTIALS_ID to its credential ID. The central runner passes that bound file to the Fastlane action as `service_credentials_file`. Configure access according to [Firebase service-account authentication](https://firebase.google.com/docs/app-distribution/authenticate-service-account).

Android debug uploads its signed APK; Android release uploads its signed AAB. For AABs, complete [Firebase's Google Play linkage and AAB prerequisites](https://firebase.google.com/docs/app-distribution/android/distribute-fastlane?apptype=aab) first. An APK does not need that linkage.

For iOS, set BUILD_MODE=release and IOS_EXPORT_METHOD to release-testing, debugging or enterprise, with matching signing material. Simulator ZIPs and app-store-connect exports are rejected for this destination. Device registration/provisioning must permit installation by the intended testers. The Mac agent must have Ruby/Bundler in its service PATH; the pipeline installs the locked upload bundle before binding credentials. Firebase CLI is not required. See [Mac setup](SETUP_MACOS.md).

UPLOAD_RELEASE_NOTES optionally supplies one line of notes, up to 500 characters. This is public release text, not a place for credentials.

<a id="google-play"></a>
## Google Play

Set ANDROID_UPLOAD_DESTINATION=google and BUILD_MODE=release. The pipeline uploads the verified AAB using central Fastlane. The app must already exist in Play Console, with initial setup completed and a suitable previously uploaded build as required by [Fastlane's Play setup](https://docs.fastlane.tools/actions/upload_to_play_store/). Configure an Android Publisher service account with access to the specific app; save its JSON as a Jenkins Secret file and reference it with GOOGLE_PLAY_CREDENTIALS_ID. Follow [Google Play API access setup](https://developers.google.com/android-publisher/getting_started).

Choose GOOGLE_PLAY_TRACK from internal, alpha, beta or production. The default is internal. GOOGLE_PLAY_RELEASE_STATUS defaults to draft; completed requests release on the selected track, subject to Play review and account/app requirements. A draft upload is not automatically available to testers. In particular, choosing production/completed can lead to a public release after Google's requirements are satisfied.

Use the correct upload signing key and an unused, increasing Android version code. The pipeline uses the app's existing version; it does not automatically increment it. UPLOAD_RELEASE_NOTES is optional and supplies the en-US changelog. Listing metadata and screenshots are not uploaded.

<a id="appstore"></a>
## App Store Connect / TestFlight

Set IOS_UPLOAD_DESTINATION=appstore, BUILD_MODE=release and IOS_EXPORT_METHOD=app-store-connect. Configure iOS distribution signing separately as described in [iOS release signing](#ios-signing).

Create the app record in App Store Connect with the matching bundle ID and prepare an API key with access to upload builds. The Jenkins Secret file must contain the Fastlane API-key JSON fields `key_id`, `issuer_id` and `key` (the private P8 contents as a JSON string with escaped newlines). A raw P8 file alone is not this JSON. Create/store the file through protected local administration; do not paste it in chat or commit it. Set APPSTORE_API_KEY_CREDENTIALS_ID to the Jenkins credential ID. See [Fastlane's API-key JSON format](https://docs.fastlane.tools/app-store-connect-api/) and [upload_to_testflight](https://docs.fastlane.tools/actions/upload_to_testflight/).

UPLOAD_RELEASE_NOTES optionally supplies TestFlight changelog text. This destination uploads the binary to App Store Connect for TestFlight. It does not submit to App Review, select external tester groups, or automatically release publicly. Apple processing, compliance questions and tester availability still need completion in App Store Connect. Use a new acceptable build number for subsequent uploads; this pipeline does not change app versioning automatically.

<a id="setup-fields"></a>
## Setup-only fields

These are not additional uppercase Jenkins job parameters. They live in answers.json or the Pipeline SCM configuration.

| Field | Possible values / example | Short description |
| --- | --- | --- |
| schema_version | Integer 1 | Current answers schema. |
| confirmed | Boolean true to execute; example starts false | Records that actual public settings were confirmed. |
| project_id | 1-80 characters; letter first, then letters/digits/dot/underscore/hyphen | Ownership marker for managed jobs/nodes; not an application ID. |
| job_name | 1-80 characters; letter first, then letters/digits/spaces/dot/underscore/hyphen; no leading/trailing spaces; e.g. Android Staging Release | Flat Jenkins job name; folder paths are not supported by the helper. |
| jenkins.url | HTTP(S) Jenkins base URL, optionally a context path; no embedded credentials/query/fragment | Target Jenkins instance. |
| jenkins.poll_schedule | Empty to disable, supported five-field Jenkins cron such as H/5 * * * *, or @hourly/@daily/@midnight/@weekly/@monthly/@yearly/@annually | Poll SCM schedule. Five-field syntax supports H/ranges/lists/positive steps within field ranges. No multiline TZ directive. |
| ci.repository_url | Same supported Git URL forms as APP_REPOSITORY_URL | This central CI repository, not the app. |
| ci.ref | Branch name, refs/heads/name, refs/tags/name, or full 40/64-character hexadecimal commit | Tooling revision. A bare name selects a branch; use refs/tags/ for a tag. Pin a reviewed version. |
| ci.script_path | Repository-relative path, normally Jenkinsfile; no traversal | Pipeline script inside central SCM. |
| ci.credentials_id | Git credential ID or empty when unnecessary | Access to central SCM; independent of APP_CREDENTIALS_ID. |

<a id="host-inputs"></a>
## Host inputs and runtime bindings

Host OS/access, Docker context/storage/port, Xcode installation and Mac node name/root are provisioning inputs, not app configuration. The node helper takes --agent-name, --remote-fs and --secret-file; see [helper workflow](#automation) and host setup for [Windows/WSL](SETUP_WINDOWS_WSL.md), [Linux](SETUP_LINUX.md) or [macOS](SETUP_MACOS.md).

| Name | Value / purpose |
| --- | --- |
| FLUTTER_VERSION | Host image/Mac preflight version; packaged example 3.47.0 |
| ANDROID_CMDLINE_TOOLS_VERSION | Numeric Android tools archive version; packaged example 15859902 |
| JENKINS_BASE_IMAGE | Host build base; packaged example jenkins/jenkins:2.568.3-jdk21 |
| JENKINS_HTTP_PORT | Available host TCP port; packaged default 8080 |
| DEVELOPER_DIR | Mac Xcode developer path, e.g. /Applications/Xcode.app/Contents/Developer |
| JENKINS_USER / JENKINS_API_TOKEN | Protected setup-helper authentication; never put secrets in public parameters or answers |
| ANDROID_KEYSTORE_FILE / ANDROID_STORE_PASSWORD / ANDROID_KEY_ALIAS / ANDROID_KEY_PASSWORD | Runtime bindings created by Jenkins from the four Android credential IDs; do not add them as public job parameters |
| IOS_P12_FILE / IOS_P12_PASSWORD / IOS_PROFILE_FILE | Runtime bindings created by Jenkins from the three iOS credential IDs; do not add them as public job parameters |
| FIREBASE_CREDENTIALS_FILE / GOOGLE_PLAY_CREDENTIALS_FILE / APPSTORE_API_KEY_FILE | Runtime secret-file bindings created only for the selected upload stage; not public parameters |

CI_ROOT, CI_COMMIT, APP_COMMIT, WORKSPACE, CI_ACTION and CI_PLATFORM are internal build context, not user configuration.

<a id="examples"></a>
## Example jobs and artifacts

| Job | App branch | ENVIRONMENT | BUILD_MODE | PLATFORM | APP_NAME | Android/iOS ID |
| --- | --- | --- | --- | --- | --- | --- |
| MyApp-Staging-Web | staging | staging | debug | web | My App Staging | com.company.app.staging |
| MyApp-Staging-Android | staging | staging | debug | android | My App Staging | com.company.app.staging |
| MyApp-Staging-iOS | main | staging | debug | ios | My App Staging | com.example.myapp |
| MyApp-Production-iOS | main | production | release | ios | My App | com.company.app |

The staging iOS row preserves the first simulator-job example: use your actual app Git URL, `API_BASE_URL=https://staging-api.example.com`, `IOS_SCHEME=Runner`, the configured `flutter-macos` node and no upload destination. Start from the complete answers template; this row alone is not a complete configuration.

These examples show selection only; fill the other required fields and appropriate signing credentials. Copy a configured central job to create another configuration, change saved values, then run once to establish that app/branch checkout for polling.

| Upload example | Saved settings in addition to required build/signing values |
| --- | --- |
| Android QA APK | `PLATFORM=android`, `BUILD_MODE=debug`, `ANDROID_UPLOAD_DESTINATION=firebase`; Firebase Android app ID, credential ID and optional groups |
| Android Play draft | `PLATFORM=android`, `BUILD_MODE=release`, `ANDROID_UPLOAD_DESTINATION=google`, `GOOGLE_PLAY_TRACK=internal`, `GOOGLE_PLAY_RELEASE_STATUS=draft`; Play credential ID |
| iOS Firebase testers | `PLATFORM=ios`, `BUILD_MODE=release`, `IOS_EXPORT_METHOD=release-testing`, `IOS_UPLOAD_DESTINATION=firebase`; Firebase iOS app ID, credential ID and optional groups |
| iOS TestFlight | `PLATFORM=ios`, `BUILD_MODE=release`, `IOS_EXPORT_METHOD=app-store-connect`, `IOS_UPLOAD_DESTINATION=appstore`; API-key credential ID |
| Web archive | `PLATFORM=web`, `WEB_UPLOAD_DESTINATION=none` |

For `PLATFORM=all`, choose Android and iOS destinations independently; Web remains `none`. A shared Firebase credential must have access to both apps if both destinations are Firebase.

Outputs are under `app/build/ci/<ENVIRONMENT>/<BUILD_MODE>/<platform>/` in the Jenkins workspace and downloadable from the build's **Artifacts** page:

| Platform | Mode | Artifact | Signing |
| --- | --- | --- | --- |
| Android | debug | `app.apk` | Normal debug signing |
| Android | release | `app.aab` | Configured Android signing |
| Web | debug or release | `app.zip` | None |
| iOS | debug | `app.zip` | Unsigned simulator archive |
| iOS | release | `app.ipa` | Apple device-release signing |

Native outputs are checked against the requested IDs/names. Each successful output also has a `SUCCESS` marker containing exactly `<environment> <mode> <platform>` followed by a newline. Upload validation requires both a nonempty artifact and a matching marker; a file merely existing does not establish a successful build. Archives remain downloadable if the later upload fails.

