# Central Flutter CI

This is the standalone central CI repository. Copy **nothing** into Flutter repositories.

Each Jenkins job selects an app repository and branch, environment, build mode, platform, app name, API URL, Android application ID and iOS bundle ID. The pipeline checks out central tooling and the app separately. Only the disposable app checkout is adapted for a build; no changes are committed or pushed to the app.

Start with [HOST_SETUP.md](HOST_SETUP.md), then [JENKINS_SETUP.md](JENKINS_SETUP.md). [IOS_SETUP.md](IOS_SETUP.md) covers Mac workers and signing. [AUTOMATION.md](AUTOMATION.md) describes setup helpers.

The original [Flutter CI-CD.pdf](requirements/Flutter%20CI-CD.pdf) and [derived handover](requirements/FLUTTER_CICD_AGENT_HANDOVER.md) are included unchanged. They provide requirements/history; the current zero-app-files request governs this implementation.

This implementation tests, builds and archives Android APK/AAB, Web output and iOS simulator ZIP/IPA. It does not upload to stores or deploy websites.

## Continuing work or configuring a job

New agents: read [AGENTS.md](AGENTS.md), then [AGENT_HANDOVER.md](AGENT_HANDOVER.md) for the design, code map, history and pending verification.

Job configuration: [PARAMETERS.md](PARAMETERS.md) lists every parameter, possible values, examples and signing requirements. Keep it alongside [JENKINS_SETUP.md](JENKINS_SETUP.md) when creating or copying jobs.

## Application compatibility

Standard Flutter Android app modules and iOS Runner projects are supported. Existing Android flavors and shared iOS schemes can be selected by parameters. Dependencies, Android namespace/source package, native plugins and application Dart source are preserved. Custom targets/extensions, multiple Android flavor dimensions and unusual layouts need a reviewed adapter **in this central repository**, never an app-side CI installation.

APP_NAME controls the Android launcher label, iOS display name and Web document/PWA metadata. An app's own in-screen title or API client changes only if existing code reads the APP_NAME/API_BASE_URL Dart defines. CI cannot replace arbitrary hardcoded Dart business logic without changing the application. Report that limitation rather than patch the app.

Create a new job for this central model. Old per-project jobs use a different pipeline. Copy central jobs and edit their saved values. [VALIDATION.md](VALIDATION.md) records executed checks and limits.
