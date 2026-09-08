# Central CI validation

Local checks on 2026-09-07:
- 11 build-runner contract tests passed.
- 16 automation tests passed: settings, separate CI/app repositories, saved job values, ownership/backups, pinned refs and Mac secret handling.
- 12 native tests passed on Linux. Windows passed 11 with one POSIX-only skip. Native tests use tool stubs; they are not real signed builds.
- Ruby syntax and a real xcodeproj operation on a disposable project copy passed, changing the iOS name/ID without touching the original.
- The central Jenkinsfile compiled with Groovy 3.0.25 without executing it. This checks language syntax, not Jenkins Declarative/runtime behavior.
- A fresh Flutter 3.47 app without CI files passed formatting, analysis, widget tests and a real Web debug build with the parameterized name.
- Package manifests, unchanged original requirements and automatic.zip are verified during assembly.

## Outstanding integration checks

Docker Desktop's engine returned HTTP 500 during concurrent Android/Gradle checks. The Android APK build and flavored-Gradle check have no confirmed result. This central version has not completed Android release compilation or real Mac/Xcode compilation/signing.

The planned isolated Jenkins app-commit/polling and fresh-bootstrap integration tests could not run while Docker was unavailable. App checkout has polling enabled, but actual automatic-trigger execution remains to be verified. Historical per-project tests do not validate this new pipeline.

Temporary containers may need cleanup after Docker recovers: flutter-central-runner-validation and the anonymous optional native Gradle fixture. No shared Docker/Jenkins restart was attempted. No live jobs or credentials were changed.

## Target acceptance

Publish only the central repository and configure a fresh central job. Verify real selected-platform artifacts, exact native names/IDs and intended release signing. Run Jenkins once and verify archived artifacts and saved parameters. Then verify an authorized app update triggers the selected branch/job with those settings. Do not push a test change into an app without authorization.

For fresh hosts verify secured bootstrap and restart persistence; for iOS verify the native worker, compilation and signing cleanup. Confirm the app Git tree receives no CI/configuration commits.

The supplied Flutter test project's app files and root Jenkinsfile were unchanged during centralization. At the end of the 2026-09-07 validation session, central tooling was local and had not been connected to a live job.

## Repository move reported 2026-09-08

The user reports creating and pushing the standalone repository at D:/Projects/GIT/flutter-cicd-central. This supersedes the earlier local-only publication status. No new live Jenkins connection, host recovery or platform/trigger validation is implied by that move. See [AGENT_HANDOVER.md](AGENT_HANDOVER.md) for continuation context.

## Optional Linux platform variable fix: 2026-09-08

A user-supplied Jenkins console log shows central tag refs/tags/v1.0.0
(commit daa5e261ae27ca88bea5cb4dc6540a85c6ed3b7d) and the app branch checking
out successfully, followed by `CI_PLATFORM: parameter not set` in Validate
App Configuration, before Docker or Flutter execution. The log reports an SCM
trigger, but does not establish which repository change triggered it.

Jenkins withEnv removes variables assigned an empty value. The Linux wrapper
now uses `${CI_PLATFORM:-}` for the optional platform check under `set -eu`.
No public parameters, platform routing or native runners changed.

Local Windows verification with Git for Windows Bash:
- The new shell regression test reproduced failures for validate and quality
  with CI_PLATFORM absent before the fix.
- After the fix, 2 shell tests passed, covering absent/empty platform values,
  explicit web/Android arguments, workspace paths containing spaces and failure
  when required CI_ACTION is missing. The actual Jenkinsfile shell body runs;
  Docker is stubbed. Run with
  `python3 -B -m unittest discover -s tests -p 'test_pipeline.py'`.
- 11 build-runner and 16 setup automation tests passed.

These checks do not execute Jenkins or real platform builds. The correction
must be published and the job's central SCM ref updated from v1.0.0 to a fixed
revision before rerunning Jenkins. No live job, release tag or app was changed.
