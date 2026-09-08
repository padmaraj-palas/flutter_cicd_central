# Troubleshooting

Errors, causes and fixes. Symptoms are grouped by where they occur.

---

## 0. Where to look first

| What | Command |
| --- | --- |
| Jenkins log (containerised) | `docker compose logs --tail=200 jenkins` |
| Jenkins log (macOS service) | `tail -50 ~/Library/Logs/local.flutter-ci.jenkins/stderr.log` |
| Mac agent log | `tail -50 ~/Library/Logs/local.flutter-ci.flutter-mac-01/stderr.log` |
| Build console | Jenkins → job → build number → **Console Output** |
| Node status | Jenkins → **Manage Jenkins → Nodes** |

**Read the exit code.** It narrows the cause quickly:

| Exit code | Meaning |
| --- | --- |
| `125` | Docker daemon rejected the run — volume/mount/image problem, container never started |
| `126` | Command found but not executable — usually macOS TCC permission |
| `127` | Command not found — `PATH` problem |
| `137` | Killed (OOM) — out of memory |

---

## 1. Preflight and prerequisites

### `This starter requires an amd64 Docker host; found aarch64`

**Cause:** `host/check-host.sh` on Apple Silicon or ARM Linux.

**Fix:** On macOS, this is expected — that script validates the containerised topology
which the macOS path does not use. Skip it and follow
[03-setup-macos.md](03-setup-macos.md), which runs the container as emulated amd64 with
a host-based controller. On ARM Linux, use an x86-64 host or accept emulation.

### `ERROR: Python 3.10+ is required.`

**Cause:** macOS ships Python 3.9.

**Fix:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12 --default
python3 --version
```
Ensure `~/.local/bin` precedes `/usr/bin` on your login `PATH`, then **reinstall any
LaunchAgent installed before this change** — it captured the old `PATH`.

### `Expected Flutter 3.47.0; found 3.47.1.`

**Cause:** `host/macos/check-host.sh` requires an **exact** match with its argument.

**Fix:** Pass your installed version: `bash host/macos/check-host.sh 3.47.1`. Also set
`FLUTTER_VERSION` in `host/.env` to the same value so container and Mac agree.

### `Missing prerequisite: <tool>`

**Fix:** Install it and make sure it's on the `PATH` of the shell running the check.
Common: `bundle` (`gem install bundler -v 4.0.20`), `pod` (`gem install cocoapods`).

### `Complete Xcode license acceptance` / `first-launch setup`

```bash
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
```

### Bundler version conflicts

**Cause:** Both `Gemfile.lock` files pin `BUNDLED WITH 4.0.20`, and uploads run with
`BUNDLE_FROZEN=true`.

**Fix:** `gem install bundler -v 4.0.20`

---

## 2. Jenkins controller

### Jenkins looks empty after moving to a service — jobs gone

**Cause:** `JENKINS_HOME` isn't set, so Jenkins used `~/.jenkins`. Your data is safe, just
not being read.

**Check:**
```bash
ps eww -p "$(pgrep -f jenkins.war)" | tr ' ' '\n' | grep JENKINS_HOME
```

**Fix:** Add `JENKINS_HOME` to the service's `EnvironmentVariables` (macOS plist) or the
container environment, then restart.

### Port 8080 already in use

```bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
```
Stop the other process, or change `JENKINS_HTTP_PORT` in `.env` (containerised) /
`--httpPort` (macOS).

### `Container 'jenkins' already exists` from `check-host.sh`

**Cause:** An existing installation. The preflight refuses to run over it.

**Fix:** Keep the existing installation and plan a migration. `--allow-existing` is
diagnostics only — it is **not** a migration command.

### Jenkins doesn't start after reboot (macOS)

**Expected.** LaunchAgents start at **login**, not at boot. Log in and they start.
Unattended-before-login needs a system `LaunchDaemon` under a dedicated CI user.

### Editing `config.xml` by hand has no effect

**Cause:** Jenkins holds configuration in memory and rewrites files on shutdown.

**Fix:** Always stop Jenkins first, edit, then start.
```bash
launchctl bootout "gui/$(id -u)/local.flutter-ci.jenkins"
# edit
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/local.flutter-ci.jenkins.plist
```

---

## 3. Agent connection

### Agent service fails instantly, exit code 126, `Operation not permitted`

```
/bin/bash: /Users/you/Desktop/.../start-agent.sh: Operation not permitted
```

**Cause:** macOS TCC blocks background services from reading `~/Desktop`, `~/Documents`
and `~/Downloads`. Interactive shells have access; `launchd` services do not.

**Fix:** Move the repository somewhere unprotected and reinstall:
```bash
launchctl bootout "gui/$(id -u)/local.flutter-ci.flutter-mac-01"
cp -R ~/Desktop/projects/flutter_cicd_central ~/ci/flutter-cicd-central
bash ~/ci/flutter-cicd-central/host/macos/install-agent.sh <url> <node> <secret> <workdir>
```

### Agent connects interactively but the service stays offline

**Cause:** `install-agent.sh` captured a `PATH` without the required tools.

**Check:**
```bash
python3 -c "
import plistlib, os
d = plistlib.load(open(os.path.expanduser('~/Library/LaunchAgents/local.flutter-ci.flutter-mac-01.plist'),'rb'))
print(d['EnvironmentVariables']['PATH'])"
```

**Fix:** Reinstall from a normal **login shell** where `python3 --version` is 3.10+ and
`flutter`, `bundle`, `git`, `java` all resolve.

### `ERROR: Secret must be readable, nonempty, owned by this user and mode 600.`

```bash
chmod 600 ~/.config/flutter-ci/agent.secret
ls -l ~/.config/flutter-ci/agent.secret
```
It must be a **regular file** (not a symlink) and **outside** the agent work directory.

### Agent rejected / immediately disconnects

**Cause:** Usually a WebSocket mismatch — `start-agent.sh` always passes `-webSocket`, so
the node must have it enabled.

**Check:**
```bash
grep webSocket ~/ci/jenkins/jenkins_home/nodes/flutter-mac-01/config.xml
```
Must be `<webSocket>true</webSocket>`. If not, stop Jenkins, `sed` it to `true`, start
Jenkins. Also confirm the secret matches the node currently in Jenkins — deleting and
recreating a node generates a **new** secret.

### `Use a new secret file; existing files and symlinks are never replaced.`

**Cause:** `macos_agent.py` refuses to overwrite.

**Fix:** Delete the old file first, or choose a new path.

---

## 4. Docker and volumes

### `failed to mkdir /var/lib/docker/volumes/flutter-pub-cache/_data/hosted: file exists`

Build fails with **exit code 125** before the container starts.

**Cause:** Docker copies image content into an **empty** named volume on first mount.
The image's `/root/.pub-cache` is populated by `flutter precache`, and that copy fails on
Docker Desktop with the containerd image store enabled.

**Fix — populate the volume explicitly:**
```bash
docker ps -aq --filter "volume=flutter-pub-cache" | xargs -r docker rm -f
docker volume rm flutter-pub-cache
docker volume create flutter-pub-cache
docker run --rm -v flutter-pub-cache:/mnt --entrypoint sh flutter-ci:1.0 \
  -c 'cp -a /root/.pub-cache/. /mnt/'
docker run --rm -v flutter-pub-cache:/root/.pub-cache --entrypoint sh flutter-ci:1.0 \
  -c 'ls -A /root/.pub-cache | wc -l'
```

> **`docker volume rm` fails silently if a container still holds the volume**, and
> `docker volume create` then no-ops on the existing one — leaving you with a
> half-populated cache and no error. Always remove holding containers first and confirm
> `rm` actually printed the volume name.

### Build container sees an empty workspace

**Cause:** Wrong mount strategy for your controller topology. `docker run -v /p:/p`
resolves the source on the **Docker host**; a containerised Jenkins keeps its workspace
in a named volume that doesn't exist at that host path, so Docker creates an empty
directory.

**Fix:** The pipeline auto-detects this via `ci_docker_run()` in the `Jenkinsfile`:
- container named `jenkins` exists → `--volumes-from jenkins`
- otherwise → `-v "$WORKSPACE:$WORKSPACE"`

If you changed this, restore it. Note the containerised controller **must** be named
exactly `jenkins`.

### `docker: command not found` in a build step

**Cause:** `docker` isn't on the Jenkins process `PATH`.

**Fix (macOS):** Docker Desktop installs to `/usr/local/bin`. Reinstall the Jenkins
LaunchAgent from a shell whose `PATH` includes it.
**Fix (containerised):** The `jenkins` image bundles the Docker CLI; verify the socket
mount with `docker exec jenkins docker version`.

### `Cannot connect to the Docker daemon`

- Docker Desktop running?
- `/var/run/docker.sock` mounted into the Jenkins container?
- On WSL2, is Docker Desktop's Ubuntu integration enabled?

### `docker compose down --volumes` deleted everything

**Cause:** That flag removes named volumes, including `flutter-cicd_jenkins_home`.

**Prevention:** Use `docker compose stop` / `start`. Take regular backups — see the
maintenance section of your setup guide.

---

## 5. Build failures

### Build queues forever, never starts

**Cause:** No online node carries the requested label.

**Check:** Compare **Manage Jenkins → Nodes** labels against the job's
`LINUX_AGENT_LABEL` / `MACOS_AGENT_LABEL`. They must match **exactly** — the node's
*name* is irrelevant.

Also: `MACOS_AGENT_LABEL` cannot be `built-in` or `master` when `PLATFORM` is `ios` or
`all`; validation rejects it.

### `OutOfMemoryError` / `Killed` / exit 137 during Gradle

**Cause:** Not enough memory for Gradle, common under emulation.

**Fix:** Raise Docker's RAM (Docker Desktop → Settings → Resources) to 10–12 GB. Reduce
the built-in node to **1 executor**. Close Xcode and other heavy apps.

### `NDK not configured` / missing NDK

```bash
docker run --rm -v flutter-ndk-cache:/opt/android-sdk/ndk \
  flutter-ci:1.0 sdkmanager "ndk;<version-your-app-needs>"
```
The image does not bake the NDK; the named volume holds it.

### Android build extremely slow on Apple Silicon

**Expected.** Gradle runs under Rosetta translation. ~6–7 minutes cold is normal;
subsequent builds are faster once `gradle-cache` warms. For native speed, use an x86-64
Linux host.

### `Missing success marker for <platform>`

**Cause:** The build script didn't complete, so the `SUCCESS` marker was never written.

**Fix:** Scroll **up** in the console output — the real error is above this line. This
message is a symptom, not the cause.

### `Built iOS bundle ID/display name does not match the selected environment`

**Cause:** `IOS_BUNDLE_ID` or `APP_NAME` doesn't match what the Xcode project produced.

**Fix:** Confirm `IOS_BUNDLE_ID` matches the app's `PRODUCT_BUNDLE_IDENTIFIER`, and that
`IOS_SCHEME` names a **shared** scheme (`ios/Runner.xcodeproj/xcshareddata/xcschemes/`).
Remember `IOS_BUNDLE_ID` forbids underscores.

### `This project requires CocoaPods`

The app has an `ios/Podfile`. Install CocoaPods on the Mac agent (`gem install
cocoapods`) and make sure `pod` is on the **service** `PATH`, then reinstall the agent.

### App checkout fails / authentication error

- Private repo → set `APP_CREDENTIALS_ID` to a valid Jenkins credential ID
- `APP_BRANCH` must be a **branch**, not a tag or PR ref
- Verify the URL is reachable from the build machine

---

## 6. Signing and uploads

### `Configure ANDROID_KEYSTORE_CREDENTIAL_ID` (or similar)

Android release with `ANDROID_RELEASE_SIGNING=jenkins` requires **all four** credential
IDs. With `project` signing they must **all be empty**.

### `An iOS release requires IOS_TEAM_ID`

Set the 10-character uppercase Team ID. Manual signing also needs `IOS_PROFILE_NAME`;
`jenkins` signing needs all three iOS credential IDs **and** `IOS_SIGNING_STYLE=manual`.

### `Existing-keychain signing uses empty Jenkins certificate/password/profile credential IDs`

Mutually exclusive settings. Either use `existing-keychain` with empty IDs, or `jenkins`
with all three set.

### `Use an explicit provisioning profile for this environment's bundle ID`

The profile's team + app ID must equal `IOS_TEAM_ID` + `IOS_BUNDLE_ID`. Wildcard or
mismatched profiles are rejected.

### `Google Play upload requires an Android release AAB`

Play accepts only `BUILD_MODE=release` output. Debug APKs are rejected.

### `iOS uploads require a signed release IPA; simulator builds cannot be uploaded`

Set `BUILD_MODE=release` with signing configured. Debug iOS produces a simulator archive.

### `App Store Connect upload requires IOS_EXPORT_METHOD=app-store-connect`

Firebase iOS uploads instead need `release-testing`, `debugging` or `enterprise`.

### `FIREBASE_ANDROID_APP_ID must be a Firebase Android app ID`

Format: `1:<digits>:android:<alphanumeric>` (or `:ios:`). Copy it from the Firebase
console. `FIREBASE_GROUPS` must be comma-separated aliases with **no spaces**.

---

## 7. Automation helper

### `Confirm the collected settings before use: schema_version=1, confirmed=true.`

Set `"confirmed": true` in `answers.json`.

### `project_id` / `job_name` rejected

Must match `[A-Za-z][A-Za-z0-9_.-]{0,79}` — start with a letter, **no spaces**.

### `Provide JENKINS_USER and JENKINS_API_TOKEN through the protected process environment.`

```bash
export JENKINS_USER=admin
read -s JENKINS_API_TOKEN && export JENKINS_API_TOKEN
```
Create the token at **your username → Security → API Token**.

### Git: `Author identity unknown`

```bash
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"
```

### Git: `could not read Username for 'https://github.com'`

Non-interactive shell can't prompt. Push from your own terminal, or configure `gh auth
login` / an SSH remote. GitHub HTTPS needs a **Personal Access Token**, not your account
password.

---

## 8. Harmless warnings

These appear in successful builds. **Ignore them.**

| Message | Explanation |
| --- | --- |
| `WARNING: The requested image's platform (linux/amd64) does not match the detected host platform` | Expected on ARM — the image runs translated. |
| `Couldn't poll for events, error = 4` / `NativeException ... executeRunLoop0` | Gradle's native file-watching can't work through a virtualised filesystem. Gradle falls back; the build completes. |
| `This version only understands SDK XML versions up to 3 but ... version 4 was encountered` | cmdline-tools slightly older than SDK metadata. Cosmetic. |
| `The SDK Manager CLI tool (sdkmanager) is deprecated` | Still functional. |
| `N packages have newer versions incompatible with dependency constraints` | Normal `pub` output. |
| `Selected Git installation does not exist. Using Default` | Jenkins falls back to `git` on `PATH`. Fine. |

---

## 9. Recovery

### Reset a single job's workspace

```bash
rm -rf <JENKINS_HOME>/workspace/<JOB_NAME>
```
Safe — the next build re-clones both repositories.

### Rebuild all caches from scratch

```bash
docker volume rm flutter-pub-cache gradle-cache flutter-ndk-cache flutter-upload-gems
# then re-run the cache provisioning steps in your setup guide
```
Slow but harmless — caches are derived data.

### Rebuild the image

```bash
cd <central-repo>/host
docker compose --profile tools build --no-cache flutter-ci
```

### Full restart

```bash
# containerised
docker compose stop jenkins && docker compose start jenkins

# macOS
launchctl kickstart -k "gui/$(id -u)/local.flutter-ci.jenkins"
launchctl kickstart -k "gui/$(id -u)/local.flutter-ci.flutter-mac-01"
```

### Verify the whole chain

| Check | Command |
| --- | --- |
| Jenkins responds | `curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/login` |
| Jenkins home correct | `ps eww -p "$(pgrep -f jenkins.war)" \| tr ' ' '\n' \| grep JENKINS_HOME` |
| Image present | `docker image inspect flutter-ci:1.0 --format '{{.Architecture}}'` |
| Toolchain works | `docker run --rm flutter-ci:1.0 flutter --version` |
| Caches populated | `docker run --rm -v flutter-pub-cache:/c alpine ls -A /c \| wc -l` |
| Agent online | `launchctl print "gui/$(id -u)/local.flutter-ci.flutter-mac-01" \| grep state` |
| Xcode selected | `xcode-select -p` |
