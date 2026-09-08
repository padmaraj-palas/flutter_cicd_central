# Invoked directly by the central runner; never loads an app Fastfile or plugins.
require "fastlane"
require "supply"
require "pilot"
if ENV.fetch("CI_UPLOAD_DESTINATION") == "google"
  Supply.config = FastlaneCore::Configuration.create(Supply::Options.available_options, {
    json_key: ENV.fetch("GOOGLE_PLAY_CREDENTIALS_FILE"),
    package_name: ENV.fetch("ANDROID_APPLICATION_ID"),
    aab: ENV.fetch("CI_UPLOAD_ARTIFACT"),
    track: ENV.fetch("GOOGLE_PLAY_TRACK"),
    release_status: ENV.fetch("GOOGLE_PLAY_RELEASE_STATUS"),
    skip_upload_apk: true, skip_upload_metadata: true,
    skip_upload_images: true, skip_upload_screenshots: true,
    skip_upload_changelogs: ENV.fetch("UPLOAD_RELEASE_NOTES", "").empty?,
    metadata_path: ENV.fetch("CI_UPLOAD_METADATA")
  })
  Supply::Uploader.new.perform_upload
else
  config = FastlaneCore::Configuration.create(Pilot::Options.available_options, {
    api_key_path: ENV.fetch("APPSTORE_API_KEY_FILE"),
    app_identifier: ENV.fetch("IOS_BUNDLE_ID"),
    ipa: ENV.fetch("CI_UPLOAD_ARTIFACT"),
    skip_waiting_for_build_processing: true,
    distribute_external: false,
    changelog: ENV.fetch("UPLOAD_RELEASE_NOTES", "")
  })
  Pilot::BuildManager.new.upload(config)
end
