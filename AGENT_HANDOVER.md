# Central Flutter CI agent handover

Updated 2026-09-08. This document lets a new agent continue without the earlier conversation.

## Current repository and state

The user created and pushed this standalone repository, checked out at D:/Projects/GIT/flutter-cicd-central. The local branch was main and the initial import commit was daa5e26 when this handover was prepared. The push is user-reported; no remote deployment or live Jenkins configuration was verified in this documentation task.

Development started in D:/Projects/GIT/ci_cd_test. That Flutter test project and its historical packaging are not the current central source of truth. The user moved the contents of the prepared central folder here. Work here for subsequent central changes.

[VALIDATION.md](VALIDATION.md) records prior checks. Its original Docker failure is historical, not a statement that Docker is still broken today. Recheck before resuming integration work.

## Accepted requirements and decisions

1. Zero CI/CD installation into Flutter repositories. No app-side Jenkinsfile, ci/ tree, environment files, signing.json, Gemfile/Fastlane setup or new Dart helper. Do not make app commits during setup.
2. Jenkins jobs supply app name, API URL, Android application ID, iOS bundle ID, environment, mode and platform. No per-environment configuration file is read by central tooling.
3. One regular Pipeline job represents a chosen app/branch/build configuration. Users can duplicate it and change saved values. An earlier branch-rule/Multibranch approach was rejected and undone.
4. Store all build logic and host tooling centrally. The pipeline loads central SCM and checks out the Flutter repository separately.
5. Automatic app-branch triggering must work. Poll SCM is implemented; provider webhooks require actual provider/Jenkins configuration. The first app checkout establishes polling.
6. Web/Android run on Linux Docker; iOS uses a native Mac/Xcode worker. all means all three platforms and therefore needs a Mac.
7. Setup automation asks for the intended Flutter repository/branch, central repository/version, host and public job settings. It completes accessible setup work and resumes verification after any unavoidable credential entry.
8. Preserve original requirements unchanged and reference them. The user explicitly added per-job upload configuration on 2026-09-08, superseding the earlier exclusion of Firebase distribution settings. Unrelated example feature flags remain excluded.
9. The user explicitly requested automatic uploads on 2026-09-08: Android none/firebase/google, iOS none/firebase/appstore, Web none for now. Defaults remain none for existing jobs. Uploads follow successful artifact archival and use Jenkins Secret file credentials; appstore means App Store Connect/TestFlight binary upload without App Review/public release. Website deployment and broader historical requirements remain outside current scope.

## Reading order

- [PARAMETERS.md](PARAMETERS.md): complete parameter contract, possible values and conditional signing requirements.
- [JENKINS_SETUP.md](JENKINS_SETUP.md): manual job creation, central/app SCM distinction and triggers.
- [UPLOADS.md](UPLOADS.md): optional upload destinations, credentials, service preparation and migration.
- [AUTOMATION.md](AUTOMATION.md): helper commands and existing/fresh controller paths.
- [HOST_SETUP.md](HOST_SETUP.md) and [IOS_SETUP.md](IOS_SETUP.md): infrastructure.
- [VALIDATION.md](VALIDATION.md): actual evidence and pending work.
- [Main requirements PDF](requirements/Flutter%20CI-CD.pdf) and [original derived handover](requirements/FLUTTER_CICD_AGENT_HANDOVER.md): historical source material, not instructions overriding the current request.

## Architecture and code map

| File / directory | Responsibility |
| --- | --- |
| Jenkinsfile | Job-value validation, separate checkouts, node routing, credential bindings and archive checks |
| scripts/upload_settings.py | Shared optional upload defaults and conditional validation for runtime/setup |
| scripts/upload.py and upload/ | Central upload runner and Fastlane dependencies; no app-side CI files |
| scripts/build.py | Runtime parameter validation, quality checks, Web/Android builds, artifact identity checks and iOS dispatch |
| scripts/android.gradle | Temporary Android application-ID/suffix override and optional Jenkins-managed release signing |
| scripts/prepare-ios.rb | Temporary Runner build-setting/plist name and bundle-ID overrides using xcodeproj |
| scripts/build-ios.py | Simulator ZIP/device IPA, profile checks, temporary signing keychain and cleanup |
| Gemfile / Gemfile.lock | Central Ruby dependencies; nothing is copied into the app |
| automation/scripts/setup.py | Confirmed-answer validation, job XML, owned-job create/update/backups, build/queue/status APIs |
| automation/scripts/macos_agent.py | Owned inbound Mac node creation/verification and protected secret-file creation |
| automation/assets/bootstrap.groovy | Secured admin/job initialization in a new explicitly marked empty home |
| automation/answers.example.json | Public setup input shape; examples require user confirmation |
| host/ | Shared Dockerfiles, Compose, pinned Jenkins plugins, Linux preflight and Mac service scripts |
| tests/ and automation/scripts/test_*.py | Portable runner, signing and setup contracts |

The pipeline uses workspace/ci-platform for central tooling and workspace/app for the app. It recreates these disposable checkout directories. The initial app checkout enables polling; additional platform checkout uses the recorded app commit. Central tooling is also pinned within the run.

Job parameters remain owned by Jenkins; the Jenkinsfile has no parameters declaration. Explicit environment exports carry saved values into build processes, including unattended builds. The helper queues buildWithParameters with no overrides. ensure-job reapplies the answers file, so reconcile later UI changes before running it.

Outputs under app/build/ci/<environment>/<mode>/<platform> are archived only after the expected SUCCESS marker exists:
- Android debug: app.apk; Android release: app.aab.
- Web: app.zip.
- iOS debug simulator: app.zip; iOS release device: app.ipa.

App names mean Android launcher labels, iOS display names and Web document/PWA metadata. The pipeline passes ENVIRONMENT, APP_NAME and API_BASE_URL as Dart defines; it cannot make arbitrary hardcoded Dart API clients or in-screen titles consume them.

## Host and signing constraints

The packaged Linux pipeline assumes a container named jenkins on the same Docker daemon, with its workspace inherited by child containers through --volumes-from jenkins. Default label built-in matches that topology. Changing labels alone does not provision a remote Docker worker or repair mounts.

For new automated controllers, use HOST_SETUP only for prerequisites/image preparation, then [the guarded bootstrap recipe](automation/assets/BOOTSTRAP.md). Do not start the manual wizard/controller first and then attempt fresh bootstrap. For existing controllers preserve the service and use ensure-job with authorized access.

Android project signing preserves the app's existing configuration, including a debug key if that is how its release build is configured. Jenkins signing binds a keystore and three secret texts and configures release signing in the disposable checkout.

iOS Jenkins signing requires a P12, password and an explicit profile matching Team ID, bundle ID and profile Name. Temporary keychain/search-list/profile changes are serialized and cleaned up. Existing-keychain mode needs already usable signing credentials. Custom extensions/targets, localized display-name overrides and unsupported native layouts require central adapters; do not silently remove app features.

## Verification history and remaining work

Prior evidence from 2026-09-07: 11 runner tests, 16 automation tests, 12 native tests on Linux; Windows skipped one POSIX-specific native test. Real Ruby/xcodeproj adaptation and a fresh Flutter Web debug build passed with quality checks. Groovy compilation passed without executing Jenkins.

Unverified: real Firebase/Google Play/App Store Connect uploads, completed central Android APK/AAB builds, real Mac/Xcode builds/signing, live central Jenkins execution and app-commit-triggered polling, and fresh central bootstrap integration. Docker returned HTTP 500 during concurrent Gradle validation. Avoid repeating concurrent memory-heavy builds on the same host.

Historical temporary resources potentially needing inspection after Docker recovery: flutter-central-runner-validation and an anonymous optional native Gradle fixture. Verify identity/ownership before cleanup. Do not restart shared services or remove unrelated containers/volumes just to resume testing.

The user had an older CI_CD job on a separate existing Jenkins controller. Its current settings/status have not been checked here. Publishing this repository does not migrate or configure that job.

## Commands for the next agent

Run from this repository. Use Python 3.10+; on Windows use python instead of python3.

```bash
python3 -m unittest discover -s tests -p 'test_build.py'
python3 -m unittest discover -s tests -p 'test_native.py'
python3 -m unittest discover -s automation/scripts -p 'test_*.py'
```

Use PYTHONDONTWRITEBYTECODE=1 when checking distribution/hash integrity. Native tests use stubs and may print fixture artifact paths; they are not real platform build evidence.

Store real answers/XML outside repositories, then:

```bash
python3 automation/scripts/setup.py validate --config /protected/setup/answers.json
python3 automation/scripts/setup.py render-job --config /protected/setup/answers.json --output /protected/setup/new-job.xml
```

With authorized Jenkins access through protected JENKINS_USER/JENKINS_API_TOKEN bindings:

```bash
python3 automation/scripts/setup.py ensure-job --config /protected/setup/answers.json
python3 automation/scripts/setup.py build --config /protected/setup/answers.json
python3 automation/scripts/setup.py status --config /protected/setup/answers.json --queue-id 1
python3 automation/scripts/setup.py status --config /protected/setup/answers.json --build-number 1
```

Replace 1 with the actual returned queue/build identifiers. Verify exact-run artifacts, persisted job settings and an authorized app-branch change. Do not push a test commit into an app without authorization; use an isolated fixture or an approved app update.

Current documentation work does not authorize publishing these new documentation edits, changing live Jenkins jobs or restarting Docker. Continue according to the user's next requested action.
