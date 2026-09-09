# macOS host setup (Apple Silicon and Intel)

This guide sets up a native Jenkins controller and iOS agent on a Mac, with Linux Docker builds for Android and Web. It also covers adding an iOS-only Mac agent to an existing controller. Use [Configuration](CONFIGURATION.md) for jobs/signing/uploads and [Operations](OPERATIONS.md) for troubleshooting, backups and validation evidence.

Other hosts: [Windows/WSL](SETUP_WINDOWS_WSL.md), [Linux](SETUP_LINUX.md).

- [Requirements and preparation](#prepare)
- [Get the central repository](#checkout)
- [Install native prerequisites and run preflight](#mac-prerequisites)
- [Start the native Jenkins controller](#mac-controller)
- [Connect and install the Mac agent](#mac-agent)
- [Add Android and Web containers](#mac-docker)
- [Configure image versions](#image-settings)
- [Provision caches](#caches)
- [Create jobs and verify builds](#first-build)

<a id="prepare"></a>
## Requirements and preparation

All CI files stay in this central repository. Jenkins checks out tooling and the app separately, adapts only its disposable app checkout and never commits or pushes app changes. Publish this repository to a Git host Jenkins can reach. Have the app repository URL/branch, display name, Android application ID and iOS bundle ID ready. Credentials belong in Jenkins or protected host bindings; configuration contains credential IDs only.

Android/Web use Linux containers on every path. iOS needs a Mac and full Xcode. The pipeline detects a container named `jenkins` on the selected Docker daemon: when present it uses `--volumes-from jenkins`; otherwise it bind-mounts the host workspace at the same absolute path. A host-run controller must not share its daemon with an unrelated `jenkins` container, which would select the wrong topology. Changing a label alone does not provision a remote Docker worker or repair its workspace mounts.

Jenkins runs directly on this Mac. Android/Web use the amd64 Linux image, emulated on Apple Silicon; iOS builds natively with Xcode. This is not a native ARM Android image. [Operations](OPERATIONS.md) preserves reported timings and the limits of recorded integration evidence.

The Mac recipe starts with 16 GB total and 100 GB free; budget RAM between macOS, Xcode and Docker. These are sizing recommendations, not guaranteed minima. Caches, image layers and archived artifacts grow over time. Serialize heavy builds.

Provide outbound access to Docker Hub, Ubuntu/Debian/Docker package repositories, GitHub, Google Flutter/Android downloads, Pub, Maven/Gradle, RubyGems, npm/NodeSource, Jenkins update/download sites, your Git server and selected upload service APIs. Configure corporate proxies/custom CA certificates in the host and relevant images when required.

Jenkins and trusted build code can control Docker on this host. Use only trusted repositories/pipeline code, keep authentication enabled and retain the localhost HTTP binding. No inbound-agent TCP port is published. A remote Mac needs an authenticated route, such as an SSH tunnel or a deliberately configured TLS reverse proxy supporting WebSockets. Localhost-only Jenkins does not receive public webhooks; use Poll SCM until ingress is configured.

**Choose your role before starting.** For a new Mac controller, follow all sections including the native controller and Docker. For an iOS-only agent joining an existing controller, preserve its home/jobs/credentials and complete only the repository checkout, native prerequisites and Mac-agent sections. Use the [existing-controller helper](CONFIGURATION.md#automation) for job management. The Linux/WSL Docker fresh-bootstrap procedure does not apply to this native controller.

<a id="checkout"></a>
## Get the central repository

Use a stable directory for the complete central checkout, including hidden files:

```bash
mkdir -p ~/ci
git clone "<your-central-repo-url>" ~/ci/flutter-cicd-central
cd ~/ci/flutter-cicd-central
```

Replace the placeholder URL; use an existing checkout if already present. On Mac avoid Desktop, Documents and Downloads, where privacy controls can block background services. No host/CI files go into Flutter repositories. [The host manifest](../manifests/host.csv) lists host deliverables/checksums; preserve `.env.example`, `.dockerignore` and other hidden files when transferring the folder.

<a id="macos"></a>
<a id="mac-prerequisites"></a>
## macOS: install native prerequisites

Use a dedicated Mac CI account on Intel or Apple Silicon. The original recipe used macOS 13+; the selected Xcode release/SDKs determine the actual required macOS version. The Mac needs its own checkout and native tools; Linux Docker workspace sharing cannot supply its checkout or build iOS.

### Xcode and Flutter

Install full Xcode from the App Store or Apple Developer Downloads, then complete selection, license and first launch:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
xcrun --sdk iphoneos --show-sdk-path
xcrun --sdk iphonesimulator --show-sdk-path
xcrun simctl list runtimes | grep -i ios
```

Verify both SDKs and an iOS simulator runtime exist. Install the selected Flutter version and add its `bin` directory (for example `~/development/flutter/bin`) to the account's login `PATH`:

```bash
flutter --version
flutter doctor
```

Match the Android/Web image's exact Flutter version. Missing native Android tooling in `flutter doctor` does not block this design because Android runs in Docker; resolve Xcode/iOS errors.

### Java, Python, Ruby and optional tools

```bash
java -version
python3 --version
ruby --version
gem install bundler -v 4.0.20
bundle --version
git --version
```

Require Java 21+ (for example Temurin 21), Python 3.10+ with SSL and Ruby 3.2+. Do not assume system Python/Ruby is recent enough. Bundler 4.0.20 is pinned in both central lockfiles; upload installation uses frozen mode.

If Python is too old, one option without Homebrew/sudo is `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12 --default
python3 --version
python3 -c "import ssl, urllib.request; print(ssl.OPENSSL_VERSION)"
```

Confirm `python3` resolves to the intended interpreter and add its executable directory to the login `PATH`; services capture this environment. Install/check CocoaPods when the app has `ios/Podfile`:

```bash
pod --version
```

For iOS Firebase and App Store Connect uploads, Ruby/Bundler must be available in the CI account's service `PATH`. The pipeline installs the locked central Fastlane bundle in `scripts/upload/Gemfile` before binding upload credentials. Firebase uses the pinned App Distribution plugin and does not require Firebase CLI or Node.js on the native Mac agent. No Fastlane/Gemfile files are installed in the app. [Configuration](CONFIGURATION.md#uploads) covers credentials/export requirements.

### Run the native preflight

From the stable central checkout, pass the exact selected Flutter version (`3.47.0` matches the packaged default; substitute a reviewed version consistently):

```bash
cd ~/ci/flutter-cicd-central
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
bash host/macos/check-host.sh 3.47.0
```

Optionally check a disposable Flutter checkout for project-specific CocoaPods requirements:

```bash
bash host/macos/check-host.sh 3.47.0 /path/to/disposable-app-checkout
```

It checks `xcodebuild`, `xcrun`, `flutter`, `java`, `ruby`, `bundle`, `git`, `python3`, `curl`, Xcode license/first-launch state, both SDKs, exact Flutter version and Java/Python/Ruby minimums. Its success message still leaves signing, simulator runtime and Jenkins connection for verification.

Optionally preinstall the native central Ruby bundle without changing the lockfile:

```bash
BUNDLE_GEMFILE="$PWD/scripts/ios/Gemfile" BUNDLE_FROZEN=true bundle install
```

If frozen installation fails, investigate the Ruby/platform selection in [Operations](OPERATIONS.md); do not discard unrelated lockfile edits. The pipeline also installs this bundle in its own tooling checkout. If using an existing controller, skip the next section and [connect the Mac agent](#mac-agent).

<a id="mac-controller"></a>
## macOS: start a native Jenkins controller

Jenkins runs directly in Java, with a separate native agent for iOS. All three platforms can run on one Mac after adding Docker. Preserve any existing controller/home instead of starting a second instance on its port.

For a new controller, download the version matching the packaged base:

```bash
mkdir -p ~/ci/jenkins
curl -fL -o ~/ci/jenkins/jenkins.war \
  https://get.jenkins.io/war-stable/2.568.3/jenkins.war
export JENKINS_HOME="$HOME/ci/jenkins/jenkins_home"
mkdir -p "$JENKINS_HOME"
java -jar ~/ci/jenkins/jenkins.war --httpPort=8080 --httpListenAddress=127.0.0.1
```

Keep localhost binding unless authenticated TLS ingress is deliberately configured. Open `http://127.0.0.1:8080`; use the console unlock password or `$JENKINS_HOME/secrets/initialAdminPassword`, choose suggested plugins, create an administrator and set the reachable Jenkins URL. Verify required plugins rather than assuming the suggested set includes everything: `git`, `workflow-aggregator`, `workflow-cps`, `workflow-job`, `pipeline-model-definition`, `credentials`, `credentials-binding`, `plain-credentials`, `timestamper`, `scm-api`, `workflow-scm-step`, `durable-task`. The complete reviewed Docker plugin set is in [host/jenkins/plugins.txt](../host/jenkins/plugins.txt).

After setup, stop foreground Jenkins with Ctrl-C. From a normal login shell create the per-user LaunchAgent. Resolve the intended Java 21+, Git and Python first; Android/Web also needs Docker on this `PATH`. The recipe refuses to overwrite an existing plist; use [Operations](OPERATIONS.md) to maintain an existing service.

```bash
LABEL="local.flutter-ci.jenkins"
LOGS="$HOME/Library/Logs/$LABEL"
mkdir -p "$LOGS" "$HOME/Library/LaunchAgents"
umask 077
if python3 - "$HOME/Library/LaunchAgents/$LABEL.plist" "$LABEL" "$LOGS" "$PATH" "$(command -v java)" <<'PY'
import os, plistlib, sys
path, label, logs, search_path, java = sys.argv[1:]
home = os.path.expanduser("~")
data = {
    "Label": label,
    "Comment": "flutter-cicd/jenkins-controller/v1",
    "ProgramArguments": [
        java, "-Djava.awt.headless=true", "-Xms256m", "-Xmx1g",
        "-jar", f"{home}/ci/jenkins/jenkins.war",
        "--httpPort=8080", "--httpListenAddress=127.0.0.1",
    ],
    "EnvironmentVariables": {
        "JENKINS_HOME": f"{home}/ci/jenkins/jenkins_home",
        "PATH": search_path, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8",
    },
    "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 30,
    "StandardOutPath": os.path.join(logs, "stdout.log"),
    "StandardErrorPath": os.path.join(logs, "stderr.log"),
}
with open(path, "xb") as output:
    plistlib.dump(data, output)
os.chmod(path, 0o600)
print("wrote", path)
PY
then
  launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/$LABEL.plist"
else
  printf '%s\n' 'Controller service file was not created; inspect the error before continuing.' >&2
fi
```

Verify state, HTTP access and saved home without dumping process environments that may contain secrets:

```bash
launchctl print "gui/$(id -u)/local.flutter-ci.jenkins" | grep -E "state|pid"
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/login
python3 - <<'PY'
import os, plistlib
path = os.path.expanduser("~/Library/LaunchAgents/local.flutter-ci.jenkins.plist")
with open(path, "rb") as source:
    print(plistlib.load(source)["EnvironmentVariables"]["JENKINS_HOME"])
PY
```

Expect HTTP 200 and `/Users/<you>/ci/jenkins/jenkins_home`; also verify the home under **Manage Jenkins > System**. An omitted `JENKINS_HOME` defaults to `~/.jenkins` and can make Jenkins appear empty.

A per-user LaunchAgent survives terminal closure and restarts a crashed process while its user session is available. It starts at login, not before login after reboot, and does not provide logout persistence. Unattended boot requires a separately configured/validated system-service arrangement, such as a LaunchDaemon under a dedicated CI account. [Operations](OPERATIONS.md) has service restart, log and backup commands.

<a id="mac-agent"></a>
## Connect a native macOS agent

### Create the node

Use a reachable controller URL over trusted HTTPS or an authenticated local SSH tunnel; reverse proxies must support WebSockets. HTTP is accepted for an explicitly trusted local route. Do not disable TLS verification or expose unauthenticated Jenkins publicly.

Under **Manage Jenkins > Nodes > New Node**, create a permanent agent, for example `flutter-mac-01`:

| Field | Value |
| --- | --- |
| Executors | `1` |
| Remote root | `/Users/<you>/jenkins-agent` |
| Labels | `flutter-macos` |
| Usage | Only build jobs with label expressions matching this node |
| Launcher | Launch agent by connecting it to the controller |
| Use WebSocket | Enabled; check Advanced if needed |

Save. It stays offline until connected. Match the label to `MACOS_AGENT_LABEL`; the example is `flutter-macos`. Pipeline routing uses labels, while launcher/helper commands use the node's name. Match the remote root to the launcher's work-directory argument.

[Configuration](CONFIGURATION.md#automation) also documents `automation/scripts/macos_agent.py`, which creates/verifies an owned node and retrieves its secret via authenticated API without printing it.

If the UI does not expose WebSocket, use the helper or this fallback **only on the native controller above**, after builds finish. Stop Jenkins before editing the existing node XML, confirm its path/name and retain a backup:

```bash
launchctl bootout "gui/$(id -u)/local.flutter-ci.jenkins"
cp -p ~/ci/jenkins/jenkins_home/nodes/flutter-mac-01/config.xml \
  ~/ci/jenkins/jenkins_home/nodes/flutter-mac-01/config.xml.before-websocket
sed -i '' 's|<webSocket>false</webSocket>|<webSocket>true</webSocket>|' \
  ~/ci/jenkins/jenkins_home/nodes/flutter-mac-01/config.xml
grep '<webSocket>true</webSocket>' ~/ci/jenkins/jenkins_home/nodes/flutter-mac-01/config.xml
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/local.flutter-ci.jenkins.plist
```

If the element is absent or verification fails, inspect the XML/helper configuration before continuing; `sed` does not create a missing element. For remote/containerized controllers use their own stopped-service procedure, not these paths.

### Save the secret and connect interactively

Store the inbound secret outside repositories and the work directory. It must be a regular file, not a symlink, owned by the CI user, nonempty and mode 600. The helper obtains it without displaying it. For manual setup, save the node page's connection secret through your protected secret-management process. If using the local clipboard:

```bash
umask 077
mkdir -p ~/.config/flutter-ci
pbpaste > ~/.config/flutter-ci/agent.secret
chmod 600 ~/.config/flutter-ci/agent.secret
```

Run `pbpaste` only with the intended secret on the clipboard. Never store it in parameters/Git/chat. From the central root connect interactively; replace `<you>`, URL and node as appropriate:

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
cd ~/ci/flutter-cicd-central
bash host/macos/start-agent.sh \
  http://127.0.0.1:8080 \
  flutter-mac-01 \
  "$HOME/.config/flutter-ci/agent.secret" \
  "$HOME/jenkins-agent"
```

For remote Jenkins use its reachable URL, for example `https://jenkins.example.internal`, rather than Mac localhost unless tunneled locally. The launcher downloads `agent.jar` from the controller and passes `-webSocket` and `-secret @/path/to/file` ([Remoting options](https://github.com/jenkinsci/remoting/blob/master/src/main/java/hudson/remoting/Launcher.java)). It stays in the foreground. Look for "WebSocket connection open" and "Connected", confirm the node is online in Jenkins, then Ctrl-C.

### Install the agent login service

Check shell paths first:

```bash
python3 --version
command -v flutter bundle git java
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
bash ~/ci/flutter-cicd-central/host/macos/install-agent.sh \
  http://127.0.0.1:8080 \
  flutter-mac-01 \
  "$HOME/.config/flutter-ci/agent.secret" \
  "$HOME/jenkins-agent"
```

Use the same tested arguments. The installer validates settings, refuses unrelated service files, captures `PATH`, Java and `DEVELOPER_DIR`, and writes `~/Library/LaunchAgents/local.flutter-ci.flutter-mac-01.plist`. Include native Flutter, Ruby/Bundler, Python, Git and optional CocoaPods binaries in its captured `PATH`. Reinstall after moving tools or the central checkout/scripts.

```bash
launchctl print "gui/$(id -u)/local.flutter-ci.flutter-mac-01" | grep -E "state|pid"
tail -n 50 "$HOME/Library/Logs/local.flutter-ci.flutter-mac-01/stderr.log"
```

It should come online and reconnect when Jenkins restarts. Unload without deleting its configuration:

```bash
launchctl bootout "gui/$(id -u)/local.flutter-ci.flutter-mac-01"
```

This is a login service, not a pre-login boot service. Online status only proves connection; compilation/signing still needs real builds. The native adapter changes only disposable Runner settings/plists. `IOS_SCHEME` selects an existing shared scheme; custom targets/extensions need a central adapter, and unsupported layouts must be reported rather than removing app features.

<a id="mac-docker"></a>
## macOS: add Android and Web containers

Skip for an iOS-only agent attached to a controller with existing Linux infrastructure.

Install [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/). Review RAM allocation: the earlier Mac recipe suggested 10-12 GB if the host can spare it, while larger Docker hosts start with 12-16 GB. Leave RAM for macOS/Xcode and increase capacity or reduce concurrency when builds exhaust memory. On Apple Silicon enable an available amd64 emulation backend; the image remains `linux/amd64` regardless of backend.

```bash
docker version
docker compose version
docker run --rm --platform linux/amd64 alpine:3.20 uname -m
```

Expect `x86_64`. Do not run `host/check-host.sh` on Apple Silicon; it checks the other controller topology. Use the native preflight and these Docker checks.

<a id="image-settings"></a>
### Configure the image

From `host/`, preserve an existing `.env` or create it once:

```bash
cd ~/ci/flutter-cicd-central/host
cp -n .env.example .env
nano .env
```

| Setting | Packaged default | Purpose |
| --- | --- | --- |
| `FLUTTER_VERSION` | `3.47.0` | Flutter Git release ref built into the image |
| `ANDROID_CMDLINE_TOOLS_VERSION` | `15859902` | Android command-line tools archive version |
| `JENKINS_BASE_IMAGE` | `jenkins/jenkins:2.568.3-jdk21` | New Docker controller base |
| `JENKINS_HTTP_PORT` | `8080` | Docker controller localhost port |

These are infrastructure settings, never credentials. Match the Mac agent's exact Flutter version. Editing `.env` does not update an existing image: rebuild and verify it. The image is `flutter-ci:1.0`; set each job's `FLUTTER_IMAGE` if choosing another.

The Flutter recipe includes Ubuntu 24.04, the selected Flutter/Dart SDK (packaged Flutter 3.47.0; verify the bundled Dart version with the smoke check), Java 17, Android platform 36/build tools, Ruby, Bundler 4.0.20, Node.js 22 and Firebase CLI 15.29.0. The runner invokes Flutter directly. Native Ruby dependencies are central in `scripts/ios/Gemfile`; Fastlane uploads use `scripts/upload/Gemfile`. The image still includes Firebase CLI, but distribution uses the locked Fastlane Firebase plugin. Uploads require the per-job settings and credentials in [Configuration](CONFIGURATION.md#firebase).

`JENKINS_BASE_IMAGE` and `JENKINS_HTTP_PORT` describe the unused Docker controller service; they do not configure the native Java process above. Do not start that service on this Mac. Upstream downloads/packages can change: image recipes are not byte-for-byte locks. For a fleet, validate reviewed images once, publish to your registry and pin approved digests. Updating an image does not migrate Jenkins.

### Build and verify the image

Set `FLUTTER_VERSION` to the Mac's exact installed version (for example `3.47.0`), then build only the Flutter image:

```bash
cd ~/ci/flutter-cicd-central/host
cp -n .env.example .env
nano .env
docker compose --profile tools config --quiet
docker compose --profile tools build flutter-ci
docker image inspect flutter-ci:1.0 --format '{{.Architecture}}/{{.Os}}'
docker run --rm flutter-ci:1.0 bash -c 'set -e
  uname -m; flutter --version; java -version
  ruby --version; bundle --version; node --version; firebase --version'
```

Expect `amd64/linux` and the selected Flutter version. The Jenkins image/service is unused on this path; do not start it. Apple Silicon runs these tools through emulation, so cold builds can take longer. The `tools` profile builds the image without running it as a service. Initial downloads span several gigabytes. Provision only where authorized to accept the Android SDK licenses accepted by the image build.

<a id="caches"></a>
### Provision caches before the first build

Install the baseline NDK in its named cache, replacing the version if the app needs another:

```bash
docker run --rm -v flutter-ndk-cache:/opt/android-sdk/ndk \
  flutter-ci:1.0 sdkmanager "ndk;28.2.13676358"
```

The image does not bake in that NDK. Existing mounts can hide image contents even after rebuilding; inspect/provision versions in the mounted cache.

On a **new, unused cache**, explicitly seed Pub to avoid the automatic image-to-volume copy failure reported with some Docker/containerd combinations (`failed to mkdir .../flutter-pub-cache/_data/hosted: file exists`):

```bash
if docker volume inspect flutter-pub-cache >/dev/null 2>&1; then
  printf '%s\n' 'Pub cache already exists; inspect it or use Operations recovery. No changes made.'
else
  docker volume create flutter-pub-cache &&
docker run --rm --mount type=volume,source=flutter-pub-cache,target=/mnt,volume-nocopy \
  --entrypoint sh flutter-ci:1.0 -ec 'cp -a /root/.pub-cache/. /mnt/' &&
docker run --rm --mount type=volume,source=flutter-pub-cache,target=/root/.pub-cache,volume-nocopy \
  --entrypoint sh flutter-ci:1.0 -ec 'test -n "$(ls -A /root/.pub-cache)"; ls -A /root/.pub-cache | wc -l'
fi
```

The count must be nonzero. For an existing in-use/damaged cache use the paused, targeted recovery in [Operations](OPERATIONS.md), not this initialization recipe. Never reset shared caches during builds. `gradle-cache` and `flutter-upload-gems` are created when used; their target paths do not contain the prepopulated Pub tree. Upload dependencies use a separate bundle cache.

### Verify controller access to Docker

Check the controller's saved environment resolves Docker/Git:

```bash
python3 - <<'PY'
import os, plistlib
path = os.path.expanduser("~/Library/LaunchAgents/local.flutter-ci.jenkins.plist")
with open(path, "rb") as source:
    search = plistlib.load(source)["EnvironmentVariables"]["PATH"].split(":")
for tool in ("docker", "git"):
    print(tool, [entry for entry in search if os.path.exists(os.path.join(entry, tool))] or "MISSING")
PY
```

Docker CLI may be in `/usr/local/bin` or a user-specific location; use the actual `command -v docker` result. If missing, follow [Operations](OPERATIONS.md) to update/reload the owned service from a correctly configured shell. Changing an interactive `PATH` alone does not update a service. Desktop must share the Jenkins workspace and selected temporary credential-file paths with Linux containers; the pipeline mounts only selected host credentials read-only.

Under **Manage Jenkins > Nodes > Built-In Node > Configure**, use one executor and allow builds there. The original Mac recipe offered a second executor, but use it only after validating capacity/concurrency; a 16 GB Mac also running Xcode should start with one. Set jobs to `LINUX_AGENT_LABEL=built-in`, `MACOS_AGENT_LABEL=flutter-macos`, `FLUTTER_IMAGE=flutter-ci:1.0`.

<a id="first-build"></a>
## Create jobs and verify the first builds

[Configuration](CONFIGURATION.md) contains every parameter, Jenkins UI instructions, confirmed answers, validate/render/apply helpers, Git credentials, signing and uploads. Store real answers/XML outside both repositories. Pipeline SCM points to this repository's root `Jenkinsfile`; job parameters select the app and tracked branch. Each copied job retains its separately configurable settings.

Suggested first checks on Mac: `PLATFORM=ios`, `BUILD_MODE=debug` (unsigned simulator ZIP), then Web, then Android. A connected agent/preflight does not establish successful builds. Release Android produces an AAB with existing app signing or Jenkins-managed keystore signing. Release iOS produces a signed IPA; Jenkins-managed signing uses an ephemeral keychain, checks profile team/app/name and cleans temporary material. Existing-keychain mode needs already usable credentials. No signing assets are bundled.

Uploads stay `none` until configured. Provider credentials are separate from signing credentials. Firebase iOS needs a suitable signed export/device provisioning; App Store Connect needs `app-store-connect` export and its own API-key JSON. App Store Connect uploading does not submit App Review or release publicly. Firebase uploading does not make an unregistered device eligible for installation. Google Play publication depends on the configured track/status. Uploads follow artifact archival; [Configuration](CONFIGURATION.md#uploads) gives exact conditions.

Run once to establish the app SCM polling baseline; repeat after changing app repository/branch. Track the exact queue/build number and verify archived artifacts, native names/IDs, intended signing and saved settings. Verify an authorized app update triggers the selected job; do not push an unrequested test app commit. [Operations](OPERATIONS.md) records dated evidence and remaining integration checks. Tool/image/startup/stub success does not prove Git authentication, Android/iOS compilation, signing, service uploads, webhooks or Mac compatibility.

