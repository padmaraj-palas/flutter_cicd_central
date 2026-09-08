# Configure automatic uploads in Jenkins

Each regular Pipeline job saves its own destination. After building, checking and archiving a platform artifact, Jenkins uploads it if that platform's destination is enabled. The same setting applies to manual and SCM-triggered builds.

| Platform | Parameter | Destinations |
| --- | --- | --- |
| Android | ANDROID_UPLOAD_DESTINATION | none, firebase, google |
| iOS | IOS_UPLOAD_DESTINATION | none, firebase, appstore |
| Web | WEB_UPLOAD_DESTINATION | none; deployment will be added later |

`none` keeps the artifact in Jenkins without uploading it. Older jobs/answers that omit the new settings behave this way. All build/upload scripts and Fastlane dependencies stay in this central repository. No CI files, Firebase SDK/config files or store metadata are installed into Flutter repositories.

## Configure a job

1. Point the job's Pipeline SCM at a reviewed central revision containing upload support. Keep the app repository/branch settings separate.
2. Open **Configure > General > This project is parameterized**. Add the upload parameters in [PARAMETERS.md](PARAMETERS.md#automatic-uploads), using one chosen value for each Choice field and saved defaults for String fields. The setup helper can render/update these fields from protected answers instead.
3. Create the selected service's **Secret file** credentials in **Manage Jenkins > Credentials**. Enter only their IDs in job settings or setup answers.
4. Configure signing and the destination requirements below. Save and build. Check both Jenkins artifacts and the destination console.

An upload failure fails the Jenkins build; already archived artifacts remain available. Service-tool output is suppressed to avoid leaking credentials; failures report the destination and exit code. Check service access, app registration, signing and version uniqueness in the destination console. Upload credentials are bound after archival, separately from signing credentials. Validation/stub tests do not prove a real service upload; [VALIDATION.md](VALIDATION.md) records actual evidence.

## Firebase App Distribution

Register the Android package name/iOS bundle ID in the intended Firebase project and enable App Distribution. Copy the Firebase **App ID** into FIREBASE_ANDROID_APP_ID or FIREBASE_IOS_APP_ID; it is different from the native package/bundle ID. Create tester groups and put their aliases in FIREBASE_GROUPS, for example `qa-team,internal-testers`, or leave it empty to upload without selecting groups. Registering an app is sufficient when only App Distribution is used; no Firebase SDK installation is needed. See the official [Android CLI guide](https://firebase.google.com/docs/app-distribution/android/distribute-cli) and [iOS CLI guide](https://firebase.google.com/docs/app-distribution/ios/distribute-cli).

Provide a service-account JSON with Firebase App Distribution permissions as a Jenkins Secret file and set FIREBASE_CREDENTIALS_ID to its credential ID. Configure access according to [Firebase service-account authentication](https://firebase.google.com/docs/app-distribution/authenticate-service-account).

Android debug uploads its signed APK; Android release uploads its signed AAB. For AABs, complete [Firebase's Google Play linkage and AAB prerequisites](https://firebase.google.com/docs/app-distribution/android/distribute-cli?apptype=aab) first. An APK does not need that linkage.

For iOS, set BUILD_MODE=release and IOS_EXPORT_METHOD to release-testing, debugging or enterprise, with matching signing material. Simulator ZIPs and app-store-connect exports are rejected for this destination. Device registration/provisioning must permit installation by the intended testers. The Mac agent must have Firebase CLI in its service PATH; see the pinned installation command in [IOS_SETUP.md](IOS_SETUP.md#optional-ios-uploads).

UPLOAD_RELEASE_NOTES optionally supplies one line of notes, up to 500 characters. This is public release text, not a place for credentials.

## Google Play

Set ANDROID_UPLOAD_DESTINATION=google and BUILD_MODE=release. The pipeline uploads the verified AAB using central Fastlane. The app must already exist in Play Console, with initial setup completed and a suitable previously uploaded build as required by [Fastlane's Play setup](https://docs.fastlane.tools/actions/upload_to_play_store/). Configure an Android Publisher service account with access to the specific app; save its JSON as a Jenkins Secret file and reference it with GOOGLE_PLAY_CREDENTIALS_ID. Follow [Google Play API access setup](https://developers.google.com/android-publisher/getting_started).

Choose GOOGLE_PLAY_TRACK from internal, alpha, beta or production. The default is internal. GOOGLE_PLAY_RELEASE_STATUS defaults to draft; completed requests release on the selected track, subject to Play review and account/app requirements. A draft upload is not automatically available to testers. In particular, choosing production/completed can lead to a public release after Google's requirements are satisfied.

Use the correct upload signing key and an unused, increasing Android version code. The pipeline uses the app's existing version; it does not automatically increment it. UPLOAD_RELEASE_NOTES is optional and supplies the en-US changelog. Listing metadata and screenshots are not uploaded.

## App Store Connect / TestFlight

Set IOS_UPLOAD_DESTINATION=appstore, BUILD_MODE=release and IOS_EXPORT_METHOD=app-store-connect. Configure iOS distribution signing separately as described in [IOS_SETUP.md](IOS_SETUP.md).

Create the app record in App Store Connect with the matching bundle ID and prepare an API key with access to upload builds. The Jenkins Secret file must contain the Fastlane API-key JSON fields `key_id`, `issuer_id` and `key` (the private P8 contents as a JSON string with escaped newlines). A raw P8 file alone is not this JSON. Create/store the file through protected local administration; do not paste it in chat or commit it. Set APPSTORE_API_KEY_CREDENTIALS_ID to the Jenkins credential ID. See [Fastlane's API-key JSON format](https://docs.fastlane.tools/app-store-connect-api/) and [upload_to_testflight](https://docs.fastlane.tools/actions/upload_to_testflight/).

UPLOAD_RELEASE_NOTES optionally supplies TestFlight changelog text. This destination uploads the binary to App Store Connect for TestFlight. It does not submit to App Review, select external tester groups, or automatically release publicly. Apple processing, compliance questions and tester availability still need completion in App Store Connect. Use a new acceptable build number for subsequent uploads; this pipeline does not change app versioning automatically.

## Examples

| Job purpose | Saved settings in addition to normal build/signing fields |
| --- | --- |
| Android QA APK | PLATFORM=android; BUILD_MODE=debug; ANDROID_UPLOAD_DESTINATION=firebase; Firebase Android app ID, credential ID and optional groups |
| Android Play draft | PLATFORM=android; BUILD_MODE=release; ANDROID_UPLOAD_DESTINATION=google; GOOGLE_PLAY_TRACK=internal; GOOGLE_PLAY_RELEASE_STATUS=draft; Play credential ID |
| iOS Firebase testers | PLATFORM=ios; BUILD_MODE=release; IOS_EXPORT_METHOD=release-testing; IOS_UPLOAD_DESTINATION=firebase; Firebase iOS app ID, credential ID and optional groups |
| iOS TestFlight upload | PLATFORM=ios; BUILD_MODE=release; IOS_EXPORT_METHOD=app-store-connect; IOS_UPLOAD_DESTINATION=appstore; App Store Connect API-key credential ID |
| Web archive | PLATFORM=web; WEB_UPLOAD_DESTINATION=none |

For PLATFORM=all, choose Android and iOS destinations independently; Web remains none. A shared Firebase credential must have permission for both configured Firebase apps when both are selected.
