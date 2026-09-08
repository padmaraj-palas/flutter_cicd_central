# Flutter CI/CD - Agent Handover and Continuation Guide

> Purpose: Give this file to a coding agent working in the Flutter
> repository. It describes the original production requirement, the POC
> completed so far, architecture decisions, and the next implementation
> direction.
>
> IMPORTANT: The current Jenkins/Docker/Fastlane setup is a POC, not the
> final production architecture. Preserve the lessons, but refactor
> toward the target architecture below.

## 1. Original Goal

Build a reusable, production-ready, on-premises Flutter CI/CD platform
using Flutter, Jenkins, Fastlane, Docker, Git-based SCM, Android, iOS,
and Web.

Required dimensions: - Environments: `testing`, `staging`,
`production` - Build modes: `debug`, `release` - Platforms: `android`,
`ios`, `web` - Total: 18 build combinations

Final Jenkins UX should eventually expose `ENVIRONMENT`, `BUILD_MODE`,
`PLATFORM`, `PROTECTION`, `DEPLOY`, version, and automatic build number.

Other requirements: automated quality gates, versioning/build numbering,
signing, artifact storage, Firebase App Distribution, Google Play,
TestFlight/App Store, Web deployment, production approval, and future
GuardSquare integration. The platform must be reusable for future
Flutter applications.

## 2. Production Architecture Target

``` text
SCM (initially GitLab)
  -> Jenkins Controller (orchestration only)
      -> Linux Docker Agent -> Android + Web
      -> macOS Agent -> iOS (Xcode + Flutter + Fastlane)
          -> Quality Gates
          -> Signing
          -> optional GuardSquare boundary
          -> Artifact Validation
          -> Artifact Repository (Nexus/Artifactory/MinIO)
          -> Firebase / Play Store / TestFlight / App Store / Web Hosting
```

Rules: 1. Controller orchestrates; heavy builds run on agents. 2.
Android/Web run in version-controlled Linux Docker agents. 3. iOS runs
on on-prem macOS. 4. Jenkins decides what to build. 5. Shared scripts
define common workflow. 6. Fastlane owns mobile-specific
build/sign/distribution. 7. Environment config has one source of truth.
8. Platform projects contain only unavoidable platform mechanics. 9.
Secrets live in Jenkins Credentials/approved secret manager. 10. Final
artifacts eventually live outside Jenkins workspace. 11. GuardSquare is
a separate optional stage/interface.

## 3. POC Completed

Windows -\> WSL2 Ubuntu -\> Docker Desktop integration. WSL user: `ci`.

Validated:

``` bash
docker run --rm hello-world
```

Troubleshooting - Docker socket permission:

``` bash
sudo usermod -aG docker $USER
newgrp docker
```

If necessary run `wsl --shutdown` from Windows and reopen Ubuntu.

## 4. Flutter CI Docker Image

POC image: `flutter-ci:1.0`, containing Ubuntu 24.04, Flutter 3.47.0,
Dart, OpenJDK 17, Android SDK/platform 36, Android Build Tools, Ruby,
Bundler, Node.js 22, Firebase CLI, Git.

Production: pin every important version and do not rely on `latest`; use
immutable versions such as `company/flutter-ci:1.0.0`.

Troubleshooting - Firebase CLI rejected Node 18.19.1. Fix: install
Node.js 22 explicitly.

Troubleshooting - Flutter required Android SDK 36. Fix: install platform
36/build tools in CI image.

Chrome/Linux desktop doctor warnings were intentionally ignored for
Android/Web compilation. Chrome is needed later for browser tests.

## 5. Real Project Validation

Succeeded inside Docker:

``` bash
flutter pub get
flutter analyze
flutter build web --release
flutter build apk --release
flutter build appbundle --release
```

Persistent caches:

``` text
flutter-pub-cache
gradle-cache
bundler-cache
```

## 6. Fastlane POC

Root Gemfile:

``` ruby
source "https://rubygems.org"
gem "fastlane"
```

Fastfile: `android/fastlane/Fastfile`. APK/AAB builds through Fastlane
succeeded.

Current simple lanes are POC only. Production direction is parameterized
operations such as `build_android(environment, build_mode)` and
deployment functions. Fastlane should own mobile build, signing,
Firebase App Distribution, Google Play, TestFlight, App Store.

## 7. Jenkins POC

Jenkins currently runs in Docker for local testing with Git + Docker
CLI. Compose mounts `jenkins_home:/var/jenkins_home` and
`/var/run/docker.sock:/var/run/docker.sock`.

Troubleshooting - Docker socket GID mismatch: get GID with:

``` bash
stat -c '%g' /var/run/docker.sock
```

Pass as `DOCKER_GID` and add Jenkins user to matching group. Do not
permanently use chmod 777.

Troubleshooting - Jenkins workspace not visible to child container:
direct `-v "$WORKSPACE:/workspace"` was problematic because Jenkins
itself is containerized. POC workaround: `--volumes-from jenkins`.

## 8. SCM POC

Current repo: `https://github.com/padmaraj-palas/ci_cd_test.git`.
Original production SCM is GitLab, but core pipeline must be
SCM-neutral.

For GitHub HTTPS with fine-grained PAT, Jenkins credential used
`Username with password`, where password is the PAT. Plain Secret Text
did not appear in Git SCM dropdown.

## 9. Automatic Build POC

SCM-triggered builds work. `all` was made the first/default platform so
automatic builds run both Web and Android:

``` groovy
choices: ['all', 'web', 'android']
```

Production should use proper GitLab webhooks, MR, branch and tag
behavior.

## 10. Current Project Layout

``` text
CI_CD/
├── android/
├── ios/
├── lib/
├── web/
├── pubspec.yaml
├── Gemfile
├── Gemfile.lock
└── Jenkinsfile
```

There is no `example/` app. Old `$WORKSPACE/example` references are
obsolete.

## 11. Current POC Pipeline

It analyzes in Docker, builds Web in Docker, builds Android through
Fastlane in Docker, archives `build/web/**` and Android AABs, and
supports all/web/android. Treat it as POC code to refactor.

# NEXT PHASE - CENTRALIZED ENVIRONMENT CONFIGURATION

## 12. Chosen Design Principle

Jenkins selects the environment. Central configuration defines the
environment. Platform files implement only platform-specific mechanics.

Do not make Jenkins the source of truth for API URLs, application IDs,
bundle IDs, app names, Firebase project names, feature flags, or web
hosts. Do not duplicate these values independently across
Android/iOS/Web.

## 13. Target Repository Structure

``` text
CI_CD/
├── android/
│   └── fastlane/Fastfile
├── ios/
├── web/
├── lib/config/app_config.dart
├── ci/
│   ├── environments/
│   │   ├── testing.env
│   │   ├── staging.env
│   │   └── production.env
│   ├── scripts/
│   │   ├── load-config.sh
│   │   ├── validate-config.sh
│   │   └── build.sh
│   └── firebase/
│       ├── android/{testing,staging,production}/
│       └── ios/{testing,staging,production}/
├── Gemfile
├── Gemfile.lock
├── Jenkinsfile
└── pubspec.yaml
```

## 14. Central Environment Files

All three files expose the same keys. Example testing:

``` bash
ENVIRONMENT=testing
APP_NAME="CI CD Test - Testing"
API_BASE_URL="https://api-testing.example.com"
ANDROID_APPLICATION_ID="com.company.cicdtest.testing"
IOS_BUNDLE_ID="com.company.cicdtest.testing"
WEB_HOST="testing.example.com"
FIREBASE_PROJECT="company-testing"
FEATURE_NEW_DASHBOARD="true"
```

Staging and production use equivalent keys with approved values.

Never commit API secrets, keystore passwords, private signing keys,
service-account credentials, App Store Connect keys, tokens, or
GuardSquare credentials. Store them in Jenkins Credentials/enterprise
secret management.

## 15. Central Dart Configuration

Create `lib/config/app_config.dart`:

``` dart
class AppConfig {
  static const String environment = String.fromEnvironment('ENVIRONMENT', defaultValue: 'testing');
  static const String apiBaseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: '');
  static const String appName = String.fromEnvironment('APP_NAME', defaultValue: 'Application');
  static const String firebaseProject = String.fromEnvironment('FIREBASE_PROJECT', defaultValue: '');
  static const bool newDashboardEnabled = bool.fromEnvironment('FEATURE_NEW_DASHBOARD', defaultValue: false);

  static bool get isTesting => environment == 'testing';
  static bool get isStaging => environment == 'staging';
  static bool get isProduction => environment == 'production';
}
```

Business code should consume AppConfig instead of embedding environment
values.

## 16. load-config.sh

Create `ci/scripts/load-config.sh`:

``` bash
#!/usr/bin/env bash
set -euo pipefail
ENVIRONMENT="${1:-}"
[ -n "$ENVIRONMENT" ] || { echo "ERROR: Environment was not provided."; exit 1; }
CONFIG_FILE="ci/environments/${ENVIRONMENT}.env"
[ -f "$CONFIG_FILE" ] || { echo "ERROR: Missing $CONFIG_FILE"; exit 1; }
set -a
source "$CONFIG_FILE"
set +a
```

Make executable with `chmod +x ci/scripts/load-config.sh`.

## 17. validate-config.sh

Create `ci/scripts/validate-config.sh`:

``` bash
#!/usr/bin/env bash
set -euo pipefail
required_variables=(ENVIRONMENT APP_NAME API_BASE_URL ANDROID_APPLICATION_ID IOS_BUNDLE_ID WEB_HOST FIREBASE_PROJECT)
for variable in "${required_variables[@]}"; do
  [ -n "${!variable:-}" ] || { echo "ERROR: Missing configuration: $variable"; exit 1; }
done
case "$ENVIRONMENT" in testing|staging|production) ;; *) echo "ERROR: Invalid environment: $ENVIRONMENT"; exit 1;; esac
```

Make executable.

## 18. Shared build.sh

Create `ci/scripts/build.sh` as the single common build entrypoint. It
receives environment, build mode, platform; loads/validates config;
constructs Dart defines; runs pub get; dispatches to Web or Fastlane
Android. Later add iOS.

Core behavior:

``` bash
./ci/scripts/build.sh testing debug web
./ci/scripts/build.sh staging release android
```

Web uses `flutter build web --$BUILD_MODE` plus central Dart defines.
Android invokes a parameterized Fastlane lane with `environment` and
`build_mode`.

## 19. Jenkins Refactor

Add independent parameters:

``` groovy
choice(name: 'ENVIRONMENT', choices: ['testing','staging','production'])
choice(name: 'BUILD_MODE', choices: ['debug','release'])
choice(name: 'PLATFORM', choices: ['all','web','android'])
```

Jenkins stages should call `./ci/scripts/build.sh` inside the CI image
instead of embedding Flutter/Gradle logic. Later add iOS, PROTECTION,
DEPLOY, version options.

## 20. Android Flavors - Thin Native Layer

Keep Android product flavors `testing`, `staging`, `production` because
the production requirement needs environment-specific native identities
and all six Android variants:

``` text
testingDebug/testingRelease
stagingDebug/stagingRelease
productionDebug/productionRelease
```

Do not duplicate API URLs, Firebase project names, feature flags, etc.
inside flavor blocks. Central config owns values; flavors provide native
variant mechanics. Where practical, Gradle should consume exported
central values such as `ANDROID_APPLICATION_ID` rather than hardcode
duplicate values.

## 21. Firebase Environment Selection

Firebase native files remain platform-specific (`google-services.json`,
`GoogleService-Info.plist`), but centralize them under `ci/firebase/...`
and have the build preparation step select/copy the correct file for the
chosen environment. Never put service-account credentials there.

## 22. Fastlane Refactor

Replace simple POC `aab` lane with parameterized build logic. Fastlane
receives environment/build mode and environment variables loaded by
shared CI scripts. Avoid copies of environment values in Fastfile.

Conceptually:

``` text
build_android(environment: staging, build_mode: release)
```

Fastlane later owns signing and deployment abstraction.

## 23. Configuration Ownership

``` text
ci/environments/*.env  = source of truth for non-secret environment values
Jenkins                = selects environment/build mode/platform and orchestrates
ci/scripts             = loads, validates, prepares and dispatches builds
Dart AppConfig          = application-visible compile-time config
Android/iOS/Web         = platform mechanics only
Fastlane                = mobile build/sign/distribution mechanics
Jenkins Credentials     = secrets
```

## 24. Immediate Implementation Order for the Coding Agent

1.  Create `ci/environments/{testing,staging,production}.env` with
    placeholder values clearly marked.
2.  Create `lib/config/app_config.dart` and demonstrate consumption
    without changing unrelated business logic.
3.  Create robust `load-config.sh` and `validate-config.sh`.
4.  Create `build.sh` and make Web work for testing/staging/production
    in debug/release.
5.  Refactor Jenkins to use ENVIRONMENT, BUILD_MODE, PLATFORM and call
    build.sh.
6.  Add thin Android flavors testing/staging/production.
7.  Make Android application identity derive from central config where
    technically sound; avoid duplicated source-of-truth values.
8.  Refactor Fastlane to a parameterized Android build lane.
9.  Add Firebase native config selection boundary (do not invent real
    Firebase files if they are unavailable).
10. Validate all 6 Web and all 6 Android combinations.
11. Do not implement iOS yet unless requested; keep the architecture
    ready for macOS agent + schemes/xcconfig.
12. Do not implement GuardSquare yet; reserve a clear optional pipeline
    interface/stage.

## 25. Quality/Security Requirements to Preserve for Later Phases

The final implementation still needs unit tests, widget tests,
integration tests where available, formatting checks, static analysis,
secret/security scanning, automated version/build number, Android/iOS
signing, build manifest, SHA-256 checksums, artifact repository,
Firebase/TestFlight/Play/App Store/Web deployment, production approval,
retry/promotion without unnecessary rebuild, rollback/recovery,
monitoring, certificate renewal, and documentation.

## 26. Agent Guardrails

-   Do not move environment values into Jenkinsfile.
-   Do not commit secrets.
-   Do not create 18 independent Jenkins jobs.
-   Do not duplicate entire Android/iOS projects per environment.
-   Do not infer production from build mode.
-   Do not infer application environment from branch inside app code.
-   Do not tightly couple GitHub/GitLab specifics into build
    scripts/Fastlane.
-   Do not use `latest` as the only CI image reference.
-   Do not build iOS in Linux Docker.
-   Do not mix GuardSquare into compilation; keep a dedicated boundary.
-   Prefer generic, parameterized functions/lanes/scripts over
    duplicated environment implementations.
-   Preserve local developer buildability: the same central config/build
    scripts should be runnable outside Jenkins where practical.

## 27. Definition of Success for the Next Phase

The next phase is successful when a developer or Jenkins can select:

``` text
ENVIRONMENT=testing|staging|production
BUILD_MODE=debug|release
PLATFORM=web|android
```

and the same central configuration source drives both platforms, while
Android retains only thin native flavor mechanics and Jenkins contains
no duplicated environment values.
