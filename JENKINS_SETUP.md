# Create a central Flutter job

See [PARAMETERS.md](PARAMETERS.md) for the full value/reference table and [AGENT_HANDOVER.md](AGENT_HANDOVER.md) for current context and verification limits.

## Publish central tooling

Create an empty Git repository on GitHub, GitLab or another reachable Git host. Copy the **contents of this central repository folder** to its root, including hidden files, and publish a reviewed version. The root contains Jenkinsfile, scripts/, automation/, host/, Gemfile and guides. Pin jobs to an approved tag or commit.

This is the only repository receiving CI/CD files. The Flutter repository is not edited.

## Configure Jenkins

1. Choose **New Item > Pipeline** and a unique name.
2. Enable **General > This project is parameterized** and add the fields below. For Choice Parameters, put **one chosen value** in Choices. For String Parameters, put the chosen job value in Default Value. Jenkins uses these saved values for unattended builds.
3. Under **Pipeline > Pipeline script from SCM > Git**, enter the **central repository URL**, its credential and version (for example refs/tags/v1.0.0). Set **Script Path: Jenkinsfile**.
4. Configure the **app** repository/branch through APP_REPOSITORY_URL and APP_BRANCH. These differ from the central Pipeline SCM fields.
5. Enable **Build Triggers > Poll SCM**, for example `H/5 * * * *`, or the agreed provider webhook integration.
6. Save and run once. This establishes app SCM polling. Verify the artifacts and actual identity.

[The automatic renderer](AUTOMATION.md) creates these fields from confirmed answers.

## Public parameters

| Parameter | Type | Value / meaning |
| --- | --- | --- |
| APP_REPOSITORY_URL | String | App's HTTPS/SSH Git URL |
| APP_BRANCH | String | One literal branch, e.g. staging |
| APP_CREDENTIALS_ID | String | Jenkins Git credential ID, or empty for public access |
| ENVIRONMENT | Choice | testing, staging or production |
| BUILD_MODE | Choice | debug or release |
| PLATFORM | Choice | android, web, ios or all (all three) |
| APP_NAME | String | My App Staging; native display name and Web metadata |
| API_BASE_URL | String | Public URL supplied as a Dart define |
| ANDROID_APPLICATION_ID | String | com.company.myapp.staging; exact Android install ID |
| IOS_BUNDLE_ID | String | com.company.myapp.staging; exact iOS bundle ID |
| ANDROID_FLAVOR | String | Empty for unflavored apps; otherwise existing flavor |
| IOS_SCHEME | String | Runner, or an existing shared scheme |
| LINUX_AGENT_LABEL | String | built-in for supplied Docker topology |
| MACOS_AGENT_LABEL | String | flutter-macos; needed for ios/all |
| FLUTTER_IMAGE | String | flutter-ci:1.0 or validated image tag/digest |
| ANDROID_RELEASE_SIGNING | Choice | jenkins or project (reuse existing signing) |
| ANDROID_KEYSTORE_CREDENTIAL_ID | String | Secret file credential ID for keystore |
| ANDROID_STORE_PASSWORD_CREDENTIAL_ID | String | Secret text credential ID |
| ANDROID_KEY_ALIAS_CREDENTIAL_ID | String | Secret text credential ID |
| ANDROID_KEY_PASSWORD_CREDENTIAL_ID | String | Secret text credential ID |
| IOS_RELEASE_SIGNING | Choice | jenkins or existing-keychain |
| IOS_TEAM_ID | String | Apple Team ID; required for iOS release |
| IOS_EXPORT_METHOD | Choice | release-testing, app-store-connect, debugging, enterprise |
| IOS_SIGNING_STYLE | Choice | manual or automatic |
| IOS_PROFILE_NAME | String | Exact profile Name for manual signing |
| IOS_CODE_SIGN_IDENTITY | Choice | Apple Distribution or Apple Development |
| IOS_P12_CREDENTIAL_ID | String | Secret file credential ID for signing P12 |
| IOS_PASSWORD_CREDENTIAL_ID | String | Secret text credential ID for P12 password |
| IOS_PROFILE_CREDENTIAL_ID | String | Secret file credential ID for profile |

Create actual credentials in **Manage Jenkins > Credentials > System > Global credentials**. Only IDs belong in parameters. Unused signing IDs may be empty. Android project signing can still use a debug key; it does not guarantee store-ready signing. iOS debug creates a simulator archive without Apple signing credentials.

APP_NAME allows 1-80 letters, digits, spaces, dots, underscores and hyphens, starting with a letter/digit. IDs are dotted identifiers. These values and API_BASE_URL are public compiled values. The common validator requires both platform IDs even for a single-platform build.

No environment or signing configuration files are read from the app. ENVIRONMENT is a build label/Dart define; it does not implicitly select native flavors. Parameters are applied only in the disposable checkout. Android namespace/source packages stay intact.

## Configure automatic uploads

In the same job parameter list, add the upload fields from [PARAMETERS.md](PARAMETERS.md#automatic-uploads). Choose a saved destination for each platform:

| Platform parameter | Choices |
| --- | --- |
| ANDROID_UPLOAD_DESTINATION | none, firebase, google |
| IOS_UPLOAD_DESTINATION | none, firebase, appstore |
| WEB_UPLOAD_DESTINATION | none |

All three default to none, including when absent from an existing job. Follow [UPLOADS.md](UPLOADS.md) to create the required service credentials and configure Firebase app IDs/groups or the Google Play track/status. Appstore uploads to App Store Connect/TestFlight without submitting to App Review. Save the choices before building; SCM-triggered builds use them too.

For existing jobs, first update Pipeline SCM to a reviewed central revision containing upload support. Add fields manually, or update the protected answers file and run ensure-job against the existing controller. Reconcile any Jenkins UI edits before ensure-job, which reapplies the answer settings. The updated renderer includes upload fields; no fresh bootstrap or app repository changes are needed.

## Automatic builds and copies

After the first successful app checkout, Poll SCM watches APP_BRANCH and queues builds using saved parameters. If the initial build fails before checkout, fix it and run once again.

For webhooks, configure the provider's Jenkins integration and reachable endpoint for the **app repository**. Entering a repository URL does not install a webhook. Poll SCM works with GitHub/GitLab without provider-specific webhook setup.

Use **New Item > Copy from**, then change repository, branch, names, IDs and other values. Run the copy once to establish its checkout. Create a fresh central job when migrating from the old per-project package; its SCM and parameter contract are different.

One build uses the same app commit across Linux/Mac and pins the tooling revision for that run. Checkouts are recreated; archived artifacts remain available.

## Artifacts

Under app/build/ci/<environment>/<mode>/<platform>: app.apk (Android debug), app.aab (Android release), app.zip (Web), app.zip (iOS simulator), app.ipa (iOS device release). Download them on the Jenkins build's Artifacts page. Native outputs are checked against requested IDs and names.

References: [SCM polling](https://plugins.jenkins.io/workflow-scm-step/), [parameters](https://www.jenkins.io/doc/book/pipeline/syntax/#parameters), [copying jobs](https://www.jenkins.io/doc/book/using/working-with-projects/).

Artifacts are archived before upload credentials are bound. A failed upload marks the build failed; the archived output remains downloadable.
