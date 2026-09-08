# Setup Path 3 — macOS

Sets up a **host-based Jenkins controller** on macOS. Builds **iOS natively** with Xcode,
and **Android + Web** inside the Linux build container.

This is the only path that can build all three platforms on one machine.

Read [README.md](README.md) first for the architecture.

---

## 1. Requirements

| Item | Requirement |
| --- | --- |
| macOS | 13 Ventura or newer |
| Hardware | Apple Silicon or Intel |
| RAM | 16 GB minimum |
| Disk | 100 GB free |
| Xcode | Full Xcode (not just Command Line Tools), first launch completed |

### 1.1 Apple Silicon reality check

`host/check-host.sh` **will refuse to run on Apple Silicon**:

```
This starter requires an amd64 Docker host; found aarch64.
```

That guard is real and intentional — the Compose recipes pin `platform: linux/amd64`,
and Google publishes no `linux-aarch64` Android SDK build-tools.

**However**, the guard protects the *containerised controller* topology. This guide uses
a different arrangement that works on Apple Silicon:

- Jenkins runs **natively on macOS**, not in a container
- The `flutter-ci` image runs as **amd64 under Rosetta translation**
- iOS builds run **natively** at full speed

Measured on an M-series Mac, 10 cores / 16 GB, Docker limited to 7.7 GB:

| Job | Time |
| --- | --- |
| iOS debug (native) | ~2–3 min |
| Web debug (emulated) | ~1 min 20 s |
| Android debug (emulated, cold Gradle cache) | ~6 min 40 s |

Usable, but Android is noticeably slower than native. On **Intel Macs** the same images
run without translation and are faster.

> **You do not need to run `host/check-host.sh`** on this path — it validates the
> containerised topology we are deliberately not using. `host/macos/check-host.sh` (a
> different script) *is* required — see section 3.

---

## 2. Install prerequisites

### 2.1 Xcode

Install from the App Store or Apple Developer Downloads, then:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
```

Verify both SDKs and a simulator runtime exist:

```bash
xcrun --sdk iphoneos --show-sdk-path
xcrun --sdk iphonesimulator --show-sdk-path
xcrun simctl list runtimes | grep -i ios
```

### 2.2 Flutter

Install Flutter and put it on your `PATH` (e.g. `~/development/flutter/bin`).

```bash
flutter --version
flutter doctor
```

Android toolchain warnings from `flutter doctor` are **expected and harmless** — Android
builds happen in the container, never on the Mac.

### 2.3 Java 21+

```bash
java -version    # must be 21 or newer
```

If missing, install Temurin 21 (Adoptium) or equivalent.

### 2.4 Python 3.10+

macOS ships Python 3.9, which the pipeline **rejects**. If `python3 --version` is below
3.10, install a newer one. Without Homebrew or `sudo`, `uv` works well:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12 --default
python3 --version        # must show 3.12.x
```

Verify SSL works — the automation helpers use `urllib` against the Jenkins API:

```bash
python3 -c "import ssl, urllib.request; print(ssl.OPENSSL_VERSION)"
```

Make sure `~/.local/bin` is on your login `PATH` (the installer appends to your shell
profile). **This matters in section 8.**

### 2.5 Ruby 3.2+ and Bundler 4.0.20

```bash
ruby --version           # must be 3.2 or newer
gem install bundler -v 4.0.20
```

Bundler **4.0.20 specifically** — both `Gemfile.lock` files pin it, and the upload
pipeline runs with `BUNDLE_FROZEN=true`.

### 2.6 CocoaPods (only if your app has `ios/Podfile`)

```bash
pod --version
```

### 2.7 Docker Desktop (only for Android/Web)

Install [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/).
In **Settings → Resources**, give it as much RAM as you can spare — 10–12 GB if
possible. Gradle under translation is memory-hungry.

```bash
docker version
docker run --rm --platform linux/amd64 alpine:3.20 uname -m   # must print x86_64
```

---

## 3. Verify prerequisites

Put the central repository somewhere **stable and outside `~/Desktop`, `~/Documents` and
`~/Downloads`**:

```bash
mkdir -p ~/ci
git clone <your-central-repo-url> ~/ci/flutter-cicd-central
cd ~/ci/flutter-cicd-central
```

> **Critical.** macOS privacy protection (TCC) blocks background `launchd` services from
> reading `~/Desktop`, `~/Documents` and `~/Downloads`. An agent installed from those
> folders fails with `Operation not permitted` and exit code 126. `~/ci` is unprotected.

Run the macOS preflight, passing **your installed Flutter version**:

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
bash host/macos/check-host.sh 3.47.1
```

It checks `xcodebuild`, `xcrun`, `flutter`, `java`, `ruby`, `bundle`, `git`, `python3`,
`curl`; Xcode licence and first-launch state; both iOS SDKs; **an exact Flutter version
match**; Java ≥ 21; Python ≥ 3.10; Ruby ≥ 3.2.

Optionally pass a Flutter project to also check CocoaPods:

```bash
bash host/macos/check-host.sh 3.47.1 /path/to/your/flutter/app
```

Expected output:

```
Host prerequisites passed for Flutter 3.47.1. Signing, simulator runtime and
Jenkins connection still require verification.
```

Pre-install the central Ruby dependencies so the first build doesn't:

```bash
BUNDLE_GEMFILE=Gemfile bundle install
```

> This may add a `bundler` checksum line to `Gemfile.lock`. Harmless — `git checkout
> Gemfile.lock` if you want the file pristine.

---

## 4. Install the Jenkins controller

Jenkins runs natively. The version below matches the base image the Compose file pins,
keeping all three paths on the same Jenkins release.

```bash
mkdir -p ~/ci/jenkins
curl -fL -o ~/ci/jenkins/jenkins.war \
  https://get.jenkins.io/war-stable/2.568.3/jenkins.war
```

Start it once in the foreground to complete setup:

```bash
export JENKINS_HOME="$HOME/ci/jenkins/jenkins_home"
mkdir -p "$JENKINS_HOME"
java -jar ~/ci/jenkins/jenkins.war --httpPort=8080 --httpListenAddress=127.0.0.1
```

`--httpListenAddress=127.0.0.1` binds to localhost only. Do not remove it without
putting authenticated TLS in front.

The console prints an unlock password (also at
`$JENKINS_HOME/secrets/initialAdminPassword`). Open **http://127.0.0.1:8080**:

1. Paste the unlock password
2. **Install suggested plugins**
3. Create your admin user
4. Set the Jenkins URL to `http://127.0.0.1:8080`

Confirm these plugins are installed (**Manage Jenkins → Plugins → Installed**):
`git`, `workflow-aggregator`, `workflow-cps`, `workflow-job`, `pipeline-model-definition`,
`credentials`, `credentials-binding`, `plain-credentials`, `timestamper`, `scm-api`,
`workflow-scm-step`, `durable-task`. "Install suggested plugins" covers all of them.

Stop Jenkins with **Ctrl-C** once the wizard is done.

---

## 5. Run Jenkins as a service

So it survives logout and restarts on crash:

```bash
LABEL="local.flutter-ci.jenkins"
LOGS="$HOME/Library/Logs/$LABEL"
mkdir -p "$LOGS" "$HOME/Library/LaunchAgents"
umask 077
python3 - "$HOME/Library/LaunchAgents/$LABEL.plist" "$LABEL" "$LOGS" "$PATH" <<'PY'
import os, plistlib, sys
path, label, logs, search_path = sys.argv[1:]
home = os.path.expanduser("~")
plistlib.dump({
    "Label": label,
    "Comment": "flutter-cicd/jenkins-controller/v1",
    "ProgramArguments": [
        "/usr/bin/java", "-Djava.awt.headless=true", "-Xms256m", "-Xmx1g",
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
}, open(path, "wb"))
os.chmod(path, 0o600)
print("wrote", path)
PY
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/$LABEL.plist"
```

> **Run this from a normal login shell.** It captures your current `PATH` into the
> service. `PATH` must contain `docker`, `git`, and Python 3.10+.

Verify:

```bash
launchctl print "gui/$(id -u)/local.flutter-ci.jenkins" | grep -E "state|pid"
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/login    # 200
ps eww -p "$(pgrep -f jenkins.war)" | tr ' ' '\n' | grep JENKINS_HOME
```

`JENKINS_HOME` **must** print `~/ci/jenkins/jenkins_home`. If it's missing, Jenkins
defaults to `~/.jenkins` and will look like a brand-new empty instance.

> **LaunchAgents start at login, not at boot.** After a reboot you must log in before CI
> comes up. Unattended-before-login requires a system `LaunchDaemon` running as a
> dedicated CI user — more setup, only worth it for a headless machine.

---

## 6. Create the macOS agent node

**Manage Jenkins → Nodes → New Node**. Name it `flutter-mac-01`, choose **Permanent
Agent**, then:

| Field | Value |
| --- | --- |
| Number of executors | `1` |
| Remote root directory | `/Users/<you>/jenkins-agent` |
| Labels | `flutter-macos` |
| Usage | *Only build jobs with label expressions matching this node* |
| Launch method | *Launch agent by connecting it to the controller* |
| Use WebSocket | **ticked** (under Advanced) |

Save. The node appears **offline** — expected until section 7.

> `flutter-macos` must match the job's `MACOS_AGENT_LABEL` **exactly**. The node's name
> is never referenced; the label is the only link.
>
> **WebSocket must be enabled** — `start-agent.sh` always passes `-webSocket`, and a
> mismatch is refused. If you can't find the checkbox, set it directly:
> ```bash
> launchctl bootout "gui/$(id -u)/local.flutter-ci.jenkins"
> sed -i '' 's|<webSocket>false</webSocket>|<webSocket>true</webSocket>|' \
>   ~/ci/jenkins/jenkins_home/nodes/flutter-mac-01/config.xml
> launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/local.flutter-ci.jenkins.plist
> ```
> Jenkins must be stopped while editing, or it will overwrite your change from memory.

---

## 7. Save the agent secret and connect

Open the node page (**Manage Jenkins → Nodes → flutter-mac-01**) and copy the long hex
secret from the displayed command. Then:

```bash
umask 077
mkdir -p ~/.config/flutter-ci
pbpaste > ~/.config/flutter-ci/agent.secret     # secret must be on your clipboard
chmod 600 ~/.config/flutter-ci/agent.secret
```

The launcher refuses the secret unless it is a regular file (not a symlink), owned by
you, mode `600`, non-empty, and **outside the agent work directory**.

Start the agent interactively first, so errors appear on screen:

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
cd ~/ci/flutter-cicd-central
bash host/macos/start-agent.sh \
  http://127.0.0.1:8080 \
  flutter-mac-01 \
  /Users/<you>/.config/flutter-ci/agent.secret \
  /Users/<you>/jenkins-agent
```

The terminal will **not** return to a prompt — that's correct. Look for:

```
INFO: WebSocket connection open
INFO: Connected
```

Confirm the node shows **online** in Jenkins, then press **Ctrl-C**.

---

## 8. Install the agent as a service

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
bash ~/ci/flutter-cicd-central/host/macos/install-agent.sh \
  http://127.0.0.1:8080 \
  flutter-mac-01 \
  /Users/<you>/.config/flutter-ci/agent.secret \
  /Users/<you>/jenkins-agent
```

> **Run from a normal login shell.** The installer snapshots your current `PATH`,
> `java` location and `DEVELOPER_DIR` into the LaunchAgent. Whatever your shell can find
> now is all the service will ever find. If `python3` resolves to macOS's 3.9 here,
> **every build will fail**. Check first:
> ```bash
> python3 --version && which flutter bundle git java
> ```

Verify:

```bash
launchctl print "gui/$(id -u)/local.flutter-ci.flutter-mac-01" | grep -E "state|pid"
tail -20 ~/Library/Logs/local.flutter-ci.flutter-mac-01/stderr.log
```

The node should come online by itself, and reconnect automatically whenever Jenkins
restarts.

**At this point iOS builds work.** Sections 9–10 add Android and Web.

---

## 9. Set up Android and Web builds

Android and Web run in the `flutter-ci` container, driven by Jenkins on the built-in node.

### 9.1 Build the image

```bash
cd ~/ci/flutter-cicd-central/host
cp -n .env.example .env
```

Edit `.env` and set `FLUTTER_VERSION` to **the same version installed on this Mac** so
iOS and Android/Web compile against one SDK:

```
FLUTTER_VERSION=3.47.1
```

Build **only** `flutter-ci` — the `jenkins` image is for the containerised topology and
is not used here:

```bash
docker compose --profile tools build flutter-ci
docker image inspect flutter-ci:1.0 --format '{{.Architecture}}/{{.Os}}'   # amd64/linux
```

Expect a long build; everything is translated. Smoke-test:

```bash
docker run --rm flutter-ci:1.0 bash -c 'set -e
  uname -m; flutter --version | head -1; java -version 2>&1 | head -1
  ruby --version; bundle --version; node --version; firebase --version'
```

> The build **auto-accepts Android SDK licences**. Use only where authorised.

### 9.2 Provision the cache volumes

**Pre-populate the pub cache explicitly.** Docker copies image content into an empty
named volume on first mount, and that copy fails on Docker Desktop with the containerd
image store enabled:

```
failed to mkdir /var/lib/docker/volumes/flutter-pub-cache/_data/hosted: file exists
```

```bash
docker volume create flutter-pub-cache
docker run --rm -v flutter-pub-cache:/mnt --entrypoint sh flutter-ci:1.0 \
  -c 'cp -a /root/.pub-cache/. /mnt/'
docker run --rm -v flutter-pub-cache:/root/.pub-cache --entrypoint sh flutter-ci:1.0 \
  -c 'ls -A /root/.pub-cache | wc -l'      # must be non-zero
```

NDK:

```bash
docker run --rm -v flutter-ndk-cache:/opt/android-sdk/ndk \
  flutter-ci:1.0 sdkmanager "ndk;28.2.13676358"
```

Only `flutter-pub-cache` needs pre-population — `gradle-cache` and
`flutter-upload-gems` mount at paths that don't exist in the image, so Docker never
attempts a copy.

### 9.3 Confirm Jenkins can reach Docker

The Linux stages run on the built-in node and shell out to `docker`, so the Jenkins
service `PATH` must include it:

```bash
python3 -c "
import plistlib, os
d = plistlib.load(open(os.path.expanduser('~/Library/LaunchAgents/local.flutter-ci.jenkins.plist'),'rb'))
p = d['EnvironmentVariables']['PATH'].split(':')
print('docker:', [x for x in p if os.path.exists(os.path.join(x,'docker'))] or 'MISSING')
print('git   :', [x for x in p if os.path.exists(os.path.join(x,'git'))] or 'MISSING')"
```

Docker Desktop installs to `/usr/local/bin`. If missing, reinstall the service
(section 5) from a shell whose `PATH` includes it.

### 9.4 Built-in node executors

**Manage Jenkins → Nodes → Built-In Node → Configure** — set **Number of executors** to
`1` or `2`. Android builds are heavy; on a 16 GB Mac also running Xcode, `1` is safer.

---

## 10. Create jobs

See [04-parameters.md](04-parameters.md) for every parameter.

Key values for this path:

| Parameter | Value | Why |
| --- | --- | --- |
| `LINUX_AGENT_LABEL` | `built-in` | Android/Web run on the Mac's Jenkins node, which drives Docker |
| `MACOS_AGENT_LABEL` | `flutter-macos` | iOS runs on the native agent |
| `FLUTTER_IMAGE` | `flutter-ci:1.0` | The image built in 9.1 |

Using the automation helper:

```bash
mkdir -p ~/ci/setup && chmod 700 ~/ci/setup
cp ~/ci/flutter-cicd-central/automation/answers.example.json ~/ci/setup/answers.json
# edit: set "confirmed": true and fill in your app's values
cd ~/ci/flutter-cicd-central
python3 automation/scripts/setup.py validate   --config ~/ci/setup/answers.json
python3 automation/scripts/setup.py render-job --config ~/ci/setup/answers.json \
    --output ~/ci/setup/job.xml
```

Apply it with an API token (**your username → Security → API Token**):

```bash
export JENKINS_USER=admin
read -s JENKINS_API_TOKEN && export JENKINS_API_TOKEN
python3 automation/scripts/setup.py ensure-job --config ~/ci/setup/answers.json
```

Or install the rendered XML directly, without a token:

```bash
launchctl bootout "gui/$(id -u)/local.flutter-ci.jenkins"
mkdir -p ~/ci/jenkins/jenkins_home/jobs/MyApp-iOS
cp ~/ci/setup/job.xml ~/ci/jenkins/jenkins_home/jobs/MyApp-iOS/config.xml
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/local.flutter-ci.jenkins.plist
```

The directory name under `jobs/` becomes the job name. Jenkins must be stopped while you
add it.

**Recommended first run**: `PLATFORM=ios`, `BUILD_MODE=debug` — an unsigned simulator
build needing no Apple credentials. Then Web, then Android.

---

## 11. Daily operations

```bash
# status
launchctl print "gui/$(id -u)/local.flutter-ci.jenkins" | grep state
launchctl print "gui/$(id -u)/local.flutter-ci.flutter-mac-01" | grep state

# restart
launchctl kickstart -k "gui/$(id -u)/local.flutter-ci.jenkins"
launchctl kickstart -k "gui/$(id -u)/local.flutter-ci.flutter-mac-01"

# logs
tail -f ~/Library/Logs/local.flutter-ci.jenkins/stderr.log
tail -f ~/Library/Logs/local.flutter-ci.flutter-mac-01/stderr.log

# stop (until next login)
launchctl bootout "gui/$(id -u)/local.flutter-ci.jenkins"
```

### Backup

Jenkins home is a plain directory here — jobs, credentials, build history, artifacts:

```bash
launchctl bootout "gui/$(id -u)/local.flutter-ci.jenkins"
tar -czf ~/ci/jenkins-home-$(date +%Y%m%d).tar.gz -C ~/ci/jenkins jenkins_home
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/local.flutter-ci.jenkins.plist
```

Backups contain credentials — restrict access.

---

## 12. Known limitations

| Limitation | Detail |
| --- | --- |
| Starts at login, not boot | LaunchAgents are per-user. Log in after a reboot. |
| Android speed | Rosetta-translated Gradle; ~6–7 min cold on Apple Silicon. Faster on Intel. |
| Docker RAM | Under the 12–16 GB the containerised paths assume. Raise it if release builds OOM. |
| Not upstream-validated | The repo's own docs state Apple Silicon Docker hosting is unsupported. This arrangement works but is outside what was validated. |
| Gradle file-watching warning | `Couldn't poll for events, error = 4` — the virtualised filesystem doesn't support native file watching. Harmless; the build completes. |
| `~/Desktop` is off-limits | TCC blocks background services. Keep everything under `~/ci`. |

---

## 13. Next steps

- [04-parameters.md](04-parameters.md) — configure your job
- [05-troubleshooting.md](05-troubleshooting.md) — when something fails
