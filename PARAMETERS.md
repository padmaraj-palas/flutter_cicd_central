# Jenkins parameters reference

This reference describes the current central implementation. Allowed choices and setup validation come from [automation/scripts/setup.py](automation/scripts/setup.py); execution comes from [Jenkinsfile](Jenkinsfile) and [scripts/build.py](scripts/build.py).

## Where to enter values

In a job, open **Configure > General > This project is parameterized**. Add Choice Parameters with **one selected value** per job, or String Parameters with the chosen value in **Default Value**. Jenkins uses these saved settings for automatic builds. The pipeline does not redefine them.

In automation, the same uppercase names are keys inside the parameters object in [answers.example.json](automation/answers.example.json). The helper requires **every listed key**, even when its explicit value is empty or the platform does not use it. Every Choice key needs a valid choice even when unused. Examples below are illustrative, not values to copy without confirmation.

All values are case-sensitive. Strings must be single-line without leading/trailing whitespace. Credential IDs accept letters, digits, underscores, dots and hyphens; they are references to credentials, not secrets.

## App source and build selection

| Parameter | Type | Possible values / example | Short description |
| --- | --- | --- | --- |
| APP_REPOSITORY_URL | String | HTTPS, ssh://user@host/path, or user@host:path Git URL; e.g. https://gitlab.com/team/app.git | Flutter repository to check out. No embedded passwords/tokens, query, fragment or whitespace. Current URL validation supports simple host/path characters, not arbitrary encoded URLs. |
| APP_BRANCH | String | Literal branch such as main, staging, feature/login or refs/heads/staging | App branch to build and poll. No wildcard, tag ref, pull-request ref or commit-selector mode. Must be a valid supported Git branch name. |
| APP_CREDENTIALS_ID | String | Credential ID such as app-git; empty for access needing no Jenkins credential | Git credentials for the app, separate from central-repository credentials. HTTPS normally uses Username with password/token; SSH uses SSH Username with private key. |
| ENVIRONMENT | Choice | testing, staging, production | Output grouping and Dart define. Does not load an environment file or automatically select a flavor. |
| BUILD_MODE | Choice | debug, release | Flutter build mode. No profile mode is exposed. |
| PLATFORM | Choice | android, web, ios, all | all runs Web, Android and iOS; a native Mac worker is required for ios/all. No comma-separated platform subsets. |

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

## Build infrastructure

| Parameter | Type | Possible values / example | Short description |
| --- | --- | --- | --- |
| LINUX_AGENT_LABEL | String | One literal label, 1-80 characters, alphanumeric first, then letters/digits/underscore/dot/hyphen; e.g. built-in | Linux execution node for Web/Android. The packaged controller/container mount topology must match; a label alone does not provision a worker. |
| MACOS_AGENT_LABEL | String | Same label format; e.g. flutter-macos. built-in and master are rejected for ios/all | Native Mac worker for iOS. Must be online with Xcode/Flutter and matching tools. |
| FLUTTER_IMAGE | String | Docker image reference, optionally registry/port, tag or sha256 digest; e.g. flutter-ci:1.0 or registry.company.com/mobile/flutter:3.47.0 | Linux build image. No whitespace, command flags or embedded credentials. Use an image already built/pulled on the correct daemon. |

The automation schema requires both labels and an image even when that platform will not execute. Image/node creation and tool installation are host setup, not effects of saving these fields.

## Android release signing

| Parameter | Type | Possible values / example | Short description |
| --- | --- | --- | --- |
| ANDROID_RELEASE_SIGNING | Choice | jenkins, project | jenkins uses bound credentials; project preserves the app's existing signing configuration. Used for Android release builds. |
| ANDROID_KEYSTORE_CREDENTIAL_ID | String | Secret file credential ID, e.g. android-release-keystore; empty when unused | Keystore file for central release signing. |
| ANDROID_STORE_PASSWORD_CREDENTIAL_ID | String | Secret text credential ID, e.g. android-store-password; empty when unused | Keystore password reference. |
| ANDROID_KEY_ALIAS_CREDENTIAL_ID | String | Secret text credential ID, e.g. android-key-alias; empty when unused | Signing key alias reference. |
| ANDROID_KEY_PASSWORD_CREDENTIAL_ID | String | Secret text credential ID, e.g. android-key-password; empty when unused | Signing key password reference. |

For android/all + release + jenkins, all four IDs must be nonempty and resolve to the stated credential types. In project mode all four central IDs must be empty in setup answers. Project signing may still use a debug key; this mode is not proof of store-ready signing. Debug builds do not bind these release credentials.

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

## Central SCM and setup-only fields

These are not additional uppercase Jenkins job parameters. They live in answers.json or the Pipeline SCM configuration.

| Field | Possible values / example | Short description |
| --- | --- | --- |
| schema_version | Integer 1 | Current answers schema. |
| confirmed | Boolean true to execute; example starts false | Records that actual public settings were confirmed. |
| project_id | 1-80 characters; letter first, then letters/digits/dot/underscore/hyphen | Ownership marker for managed jobs/nodes; not an application ID. |
| job_name | Same format as project_id; e.g. MyApp-Staging-Web | Flat Jenkins job name; folder paths are not supported by the helper. |
| jenkins.url | HTTP(S) Jenkins base URL, optionally a context path; no embedded credentials/query/fragment | Target Jenkins instance. |
| jenkins.poll_schedule | Empty to disable, supported five-field Jenkins cron such as H/5 * * * *, or @hourly/@daily/@midnight/@weekly/@monthly/@yearly/@annually | Poll SCM schedule. Five-field syntax supports H/ranges/lists/positive steps within field ranges. No multiline TZ directive. |
| ci.repository_url | Same supported Git URL forms as APP_REPOSITORY_URL | This central CI repository, not the app. |
| ci.ref | Branch name, refs/heads/name, refs/tags/name, or full 40/64-character hexadecimal commit | Tooling revision. A bare name selects a branch; use refs/tags/ for a tag. Pin a reviewed version. |
| ci.script_path | Repository-relative path, normally Jenkinsfile; no traversal | Pipeline script inside central SCM. |
| ci.credentials_id | Git credential ID or empty when unnecessary | Access to central SCM; independent of APP_CREDENTIALS_ID. |

## Host-only inputs and protected bindings

Host OS/access, Docker context/storage/port, Xcode installation and Mac node name/root are provisioning inputs, not app configuration. The node helper takes --agent-name, --remote-fs and --secret-file; see [AUTOMATION.md](AUTOMATION.md).

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

CI_ROOT, CI_COMMIT, APP_COMMIT, WORKSPACE, CI_ACTION and CI_PLATFORM are internal build context, not user configuration.

## Example jobs

| Job | App branch | ENVIRONMENT | BUILD_MODE | PLATFORM | APP_NAME | Android/iOS ID |
| --- | --- | --- | --- | --- | --- | --- |
| MyApp-Staging-Web | staging | staging | debug | web | My App Staging | com.company.app.staging |
| MyApp-Staging-Android | staging | staging | debug | android | My App Staging | com.company.app.staging |
| MyApp-Production-iOS | main | production | release | ios | My App | com.company.app |

These examples show selection only; fill the other required fields and appropriate signing credentials. Copy a configured central job to create another configuration, change saved values, then run once to establish that app/branch checkout for polling.
