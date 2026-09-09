# Invoked directly by the central runner; loads only central, locked dependencies.
require "fastlane"
case ENV.fetch("CI_UPLOAD_DESTINATION")
when "firebase"
  require "fastlane/plugin/firebase_app_distribution"
  action = Fastlane::Actions::FirebaseAppDistributionAction
  options = {
    app: ENV.fetch("FIREBASE_#{ENV.fetch('CI_UPLOAD_PLATFORM').upcase}_APP_ID"),
    service_credentials_file: ENV.fetch("FIREBASE_CREDENTIALS_FILE"),
    groups: ENV.fetch("FIREBASE_GROUPS", ""),
    release_notes: ENV.fetch("UPLOAD_RELEASE_NOTES", ""),
    debug: false
  }
  artifact = ENV.fetch("CI_UPLOAD_ARTIFACT")
  case ENV.fetch("CI_UPLOAD_PLATFORM")
  when "android"
    options[:android_artifact_path] = artifact
    options[:android_artifact_type] = File.extname(artifact).delete_prefix(".").upcase
  when "ios"
    options[:ipa_path] = artifact
  else
    abort "Unsupported Firebase upload platform"
  end
  action.run(FastlaneCore::Configuration.create(action.available_options, options))
when "google"
  require "supply"
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
when "appstore"
  require "pilot"
  config = FastlaneCore::Configuration.create(Pilot::Options.available_options, {
    api_key_path: ENV.fetch("APPSTORE_API_KEY_FILE"),
    app_identifier: ENV.fetch("IOS_BUNDLE_ID"),
    ipa: ENV.fetch("CI_UPLOAD_ARTIFACT"),
    skip_waiting_for_build_processing: true,
    distribute_external: false,
    changelog: ENV.fetch("UPLOAD_RELEASE_NOTES", "")
  })
  Pilot::BuildManager.new.upload(config)
else
  abort "Unsupported upload destination"
end
