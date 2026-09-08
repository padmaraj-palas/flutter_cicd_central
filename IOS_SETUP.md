# Native Mac worker

Use an existing reachable Jenkins controller and dedicated Mac CI user. Install compatible Flutter, full Xcode/iOS SDKs, Java 21+, Ruby 3.2+ with Bundler 4.0.20, Python 3.10+, Git and CocoaPods when needed. Select Xcode through DEVELOPER_DIR and complete first-launch/license setup.

The Flutter repository stays unchanged. The central adapter modifies only the disposable Runner project settings/plist. IOS_SCHEME selects an existing shared scheme; no new flavor files are added. Custom app targets/extensions need a central adapter.

1. **Manage Jenkins > Nodes > New Node**: permanent node, one executor, exclusive use, label flutter-macos, dedicated remote root such as /Users/ci/jenkins-agent, inbound launcher with WebSocket.
2. Save its connection secret to a protected file outside repositories and the remote root, owned by the CI user, mode 600. The automatic node helper can retrieve it without printing it.
3. Keep host/macos in a stable Mac directory:

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
bash host/macos/check-host.sh 3.47.0 /path/to/disposable-app-checkout
bash host/macos/start-agent.sh https://jenkins.company.com flutter-mac-01 /Users/ci/.config/flutter-ci/agent.secret /Users/ci/jenkins-agent
```

Confirm the node is online, stop the interactive process, then install persistence:

```bash
bash host/macos/install-agent.sh https://jenkins.company.com flutter-mac-01 /Users/ci/.config/flutter-ci/agent.secret /Users/ci/jenkins-agent
```

The user service captures PATH/Java/Xcode settings and runs after login. Verify required tools in that PATH. Pre-login boot requires separate system-service setup.

The pipeline installs the **central** Gemfile dependencies. No Gemfile or Fastlane files are added to the app. Set APP_NAME/IOS_BUNDLE_ID/IOS_SCHEME and the signing fields from [JENKINS_SETUP.md](JENKINS_SETUP.md).

Jenkins release signing uses an ephemeral keychain, validates profile team/app/name, exports/verifies the IPA and cleans temporary signing material. Existing-keychain mode needs already usable credentials. Debug creates an unsigned simulator ZIP. Store upload is separate.

Validate real simulator and release builds on the Mac. Windows/Linux adapter tests cannot prove Xcode compilation or signing works.
