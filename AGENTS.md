# Working in this repository

This is the standalone central Flutter CI repository. Read [AGENT_HANDOVER.md](AGENT_HANDOVER.md) before implementation and [PARAMETERS.md](PARAMETERS.md) before changing job configuration.

## Product requirements

- Keep CI/CD tooling in this repository. Do not install Jenkinsfiles, CI scripts, environment/signing files, Gemfiles, Fastlane files or Dart configuration helpers into Flutter repositories.
- App repositories are read-only source. Native identity changes belong only in disposable build checkouts. Do not commit or push app changes as a setup step.
- Each regular Jenkins Pipeline job owns its settings: app repository/branch, environment, mode, platform, app name, API URL and Android/iOS IDs. Preserve separate configurable jobs and copying jobs. Do not restore hardcoded Jenkinsfile parameter defaults or branch-rule/Multibranch configuration.
- Central Pipeline SCM and app SCM are distinct. Preserve app-branch polling and the same app/tooling revisions across Linux/Mac within one run.
- Keep secrets in Jenkins credentials or protected host bindings. Parameters and setup answers contain credential IDs, never credential values.
- Native labels/IDs can be adapted in the temporary checkout. Existing Dart code must already consume defines for API/in-screen title changes; report incompatibility instead of editing the app.

These record the accepted design. A later explicit user request can change scope; do not silently infer such a change from historical requirement documents.

## Work and verification

- Inspect current Git status, code and [VALIDATION.md](VALIDATION.md). The handover records history, not current host health or proof of live setup.
- Preserve existing Jenkins data/jobs and unrelated changes. Fresh bootstrap is only for an explicitly new empty home; use the existing-controller helper for an existing instance.
- Use multiple agents when useful, with coordinator, host/Jenkins, native tooling and verifier roles. Assign exclusive ownership of files/services. Serialize memory-heavy Gradle builds and builds sharing a checkout.
- For configuration/behavior changes, check the pipeline, setup validator/renderer, native runners and examples together. Keep PARAMETERS.md aligned with automation/scripts/setup.py and runtime validation.
- Run checks appropriate to the change. Documentation-only changes need link, parameter-coverage and manifest verification, not Flutter builds. Commands for behavioral checks are in AGENT_HANDOVER.md.
- Do not claim Groovy parsing or stub tests establish Jenkins/Android/iOS integration success. Update validation records with dates and actual evidence.
- Refresh FILES.csv after changes. It covers repository deliverables, excludes itself and .git, and must not inventory local answers, credentials or build/cache output. Preserve the original requirements and their hashes.
- This repository is now the working source for central CI. Do not edit the older ci_cd_test distribution copies unless the user asks for a new distribution.

Use the user's existing authorization and complete routine reversible work without unnecessary confirmation. Ask for missing target/configuration information when needed; request no secrets in chat.
