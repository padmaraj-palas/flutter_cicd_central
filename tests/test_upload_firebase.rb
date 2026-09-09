# Run with BUNDLE_GEMFILE=scripts/upload/Gemfile bundle exec ruby tests/test_upload_firebase.rb.
# Uses the installed plugin and its real option validators; publishing is stubbed.
require "tmpdir"
require "fastlane"
require "fastlane/plugin/firebase_app_distribution"

ACTION = Fastlane::Actions::FirebaseAppDistributionAction
RUNNER = File.expand_path("../scripts/upload/run.rb", __dir__)

class << ACTION
  attr_accessor :captured

  def run(config)
    self.captured = config.values
  end
end

def verify(condition, message)
  raise message unless condition
end

Dir.mktmpdir("firebase-runner-test-") do |work|
  credential = File.join(work, "service account.json")
  File.write(credential, "{}")
  ENV.update("CI_UPLOAD_DESTINATION" => "firebase", "FIREBASE_CREDENTIALS_FILE" => credential)
  [["android", "apk"], ["android", "aab"], ["ios", "ipa"]].each do |platform, extension|
    artifact = File.join(work, "app.#{extension}")
    File.write(artifact, "fixture")
    ENV.update("CI_UPLOAD_PLATFORM" => platform, "CI_UPLOAD_ARTIFACT" => artifact,
               "FIREBASE_#{platform.upcase}_APP_ID" => "1:123:#{platform}:abc")
    [false, true].each do |optional|
      ENV["FIREBASE_GROUPS"] = optional ? "qa,staff" : ""
      ENV["UPLOAD_RELEASE_NOTES"] = optional ? "New build" : ""
      load RUNNER
      options = ACTION.captured
      verify(options[:app] == "1:123:#{platform}:abc", "Wrong Firebase app")
      verify(options[:service_credentials_file] == credential, "Wrong credential")
      verify(options[:groups] == ENV["FIREBASE_GROUPS"], "Wrong tester groups")
      verify(options[:release_notes] == ENV["UPLOAD_RELEASE_NOTES"], "Wrong release notes")
      verify(options[:debug] == false, "Debug diagnostics enabled")
      if platform == "android"
        verify(options[:android_artifact_path] == artifact, "Wrong Android artifact")
        verify(options[:android_artifact_type] == extension.upcase, "Wrong Android type")
        verify(options[:ipa_path].nil?, "Unexpected iOS artifact")
      else
        verify(options[:ipa_path] == artifact, "Wrong IPA")
        verify(options[:android_artifact_path].nil?, "Unexpected Android artifact")
      end
    end
  end
end
puts "Firebase Fastlane: 6 artifact/options cases passed (publishing stubbed)."
