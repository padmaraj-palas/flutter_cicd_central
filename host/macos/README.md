# Native macOS Jenkins agent

Use this folder on a dedicated Mac account. Keep it in a stable location. Follow [IOS_SETUP.md](../../IOS_SETUP.md) for Xcode, Flutter, Ruby/Bundler, Java 21+, Python 3.10+, signing and disposable native checkout adaptation. Install CocoaPods when the app requires it.

From the configured shell, select your Xcode installation and verify prerequisites:

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
bash check-host.sh 3.47.0 /Users/ci/projects/my_app
```

Create the inbound WebSocket node using the manual iOS guide or the automatic package's `automation/scripts/macos_agent.py`. Use one executor, exclusive scheduling and the `flutter-macos` label. The remote filesystem must match the work-directory argument below.

Store the inbound secret outside the application repository and outside the agent work directory. It must belong to the agent user, be nonempty and have mode 600. The automatic helper obtains it through the authenticated Jenkins API without printing it. For manual setup, save the node's connection secret directly into a protected file through your secret-management process.

Start the agent:

```bash
bash start-agent.sh \
  https://jenkins.example.internal \
  flutter-mac-01 \
  /Users/ci/.config/flutter-ci/agent.secret \
  /Users/ci/jenkins-agent
```

The launcher downloads agent.jar from the chosen controller and passes the secret as `-secret @/path/to/file`. Use a trusted HTTPS connection or an authenticated local SSH tunnel. HTTP is accepted for an explicitly chosen trusted route; do not expose the controller publicly or disable TLS verification. The proxy must support WebSockets. Jenkins's [Remoting launcher source](https://github.com/jenkinsci/remoting/blob/master/src/main/java/hudson/remoting/Launcher.java) defines agent connection options.

Confirm the node is online in Jenkins, stop the interactive process, then install persistence with the same arguments:

```bash
bash install-agent.sh \
  https://jenkins.example.internal \
  flutter-mac-01 \
  /Users/ci/.config/flutter-ci/agent.secret \
  /Users/ci/jenkins-agent
```

This creates `~/Library/LaunchAgents/local.flutter-ci.flutter-mac-01.plist`. The installer validates the launcher settings first, refuses unrelated service files, and captures PATH, the Java executable and DEVELOPER_DIR. Ensure that PATH includes native Flutter, Ruby/Bundler, Python and Git binaries. Reinstall after changing tool locations or moving these scripts.

A per-user LaunchAgent starts when the dedicated user logs in. It does not start before login following reboot. If unattended boot is required, configure and validate the agreed system-service arrangement separately.

```bash
launchctl print gui/$(id -u)/local.flutter-ci.flutter-mac-01
tail -n 50 "$HOME/Library/Logs/local.flutter-ci.flutter-mac-01/stderr.log"
```

Unload without deleting its configuration:

```bash
launchctl bootout gui/$(id -u)/local.flutter-ci.flutter-mac-01
```

The Mac needs its own checkout; Docker workspace sharing cannot supply it. These host scripts do not install Apple signing assets. Complete the real native builds for the selected job configurations and verify their artifacts.
