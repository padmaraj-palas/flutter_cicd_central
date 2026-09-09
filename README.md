# Central Flutter CI/CD

One central repository builds Flutter apps for Web, Android and iOS. Each regular
Jenkins Pipeline job owns its app repository/branch, environment, build mode,
platform, app name, API URL, native IDs, signing and upload settings. Copy a job to
create another configuration.

App repositories receive no CI files. Jenkins checks out tooling and app source
separately, adapts only the disposable native checkout, and never commits app changes.

## Start here

| Guide | What it covers |
| --- | --- |
| [Windows/WSL setup](documents/SETUP_WINDOWS_WSL.md) | WSL2, Docker Desktop, Jenkins, build images/caches and optional Mac agent |
| [Linux setup](documents/SETUP_LINUX.md) | Ubuntu, Docker Engine, Jenkins, build images/caches and optional Mac agent |
| [macOS setup](documents/SETUP_MACOS.md) | Apple Silicon/Intel, native Jenkins and iOS agent, Docker for Android/Web |
| [Configuration](documents/CONFIGURATION.md) | Create/copy jobs, all 42 parameters, setup helpers, credentials, signing and automatic uploads |
| [Operations](documents/OPERATIONS.md) | Architecture, troubleshooting, backups, upgrades, file map, developer checks and dated validation evidence |

For a fresh **Apple Silicon Mac**, begin with [Mac setup](documents/SETUP_MACOS.md).
Jenkins runs on the Mac; Web/Android build in the amd64 Linux image under emulation,
and iOS builds natively with Xcode. Windows/Linux can build Web/Android and use a
separate native Mac agent for iOS. Existing Jenkins installations use the
[existing-controller helper](documents/CONFIGURATION.md#automation).

Download the [Jenkins parameter CSV](documents/PARAMETERS.csv) for all 42 parameters, expected values and descriptions.

## Build output and uploads

| Platform | Debug | Release | Optional automatic upload |
| --- | --- | --- | --- |
| Android | APK or AAB (default APK) | APK or AAB (default AAB) | `none`, `firebase`, `google` |
| iOS | Unsigned simulator ZIP | Signed IPA | `none`, `firebase`, `appstore` |
| Web | Web ZIP | Web ZIP | `none` |

Select Android format with `ANDROID_ARTIFACT_TYPE=apk` or `aab`. Uploads default to `none`. `appstore` uploads to App Store Connect/TestFlight; it does
not submit to App Review or release publicly. Credentials stay in Jenkins/protected
host bindings. Job settings contain credential IDs, never secrets.

`APP_NAME` changes launcher/display/Web metadata. Existing Dart code must consume
`APP_NAME` and `API_BASE_URL` defines to change in-screen titles or API behavior;
CI reports hardcoded app incompatibility rather than rewriting business logic.
Standard Android app modules and iOS Runner projects are supported; unusual native
layouts need a reviewed central adapter.

## Repository layout

- `Jenkinsfile`: stable Pipeline SCM entrypoint.
- `scripts/`: build/upload runners; Android, iOS and upload support grouped by purpose.
- `automation/`: public answers example, Jenkins helpers and fresh-bootstrap asset.
- `host/`: Docker images/Compose and stable Mac service scripts.
- `tests/`: all runner, pipeline and setup tests.
- `documents/`: three host setup guides plus shared configuration and operations guides.
- `requirements/`: unchanged original [PDF](requirements/Flutter%20CI-CD.pdf) and
  [derived handover](requirements/FLUTTER_CICD_AGENT_HANDOVER.md), retained as historical requirements.
- `manifests/` and `FILES.csv`: deliverable and original-requirement hashes.

Contributors: read [AGENTS.md](AGENTS.md) and the
[development checks](documents/OPERATIONS.md#development). See the
[migration map](documents/OPERATIONS.md#repository-history) for former document/script
locations. The [validation record](documents/OPERATIONS.md#validation) distinguishes
local checks from pending live Jenkins, Android, Mac signing and upload verification.
