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

The supplied Flutter test project's app files and root Jenkinsfile remain unchanged. The central repository is prepared locally, not published or connected to a live job.
