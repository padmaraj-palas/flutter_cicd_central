# Operations, troubleshooting and maintenance

Use the [Windows/WSL](SETUP_WINDOWS_WSL.md), [Linux](SETUP_LINUX.md) or
[macOS](SETUP_MACOS.md) setup guide to provision a host and [configuration](CONFIGURATION.md) to
create jobs, select signing and enable uploads. Commands here run from the central
repository root unless a block explicitly changes directory. Replace example paths,
node names and volume names with the values used by your installation.

- [Architecture and application compatibility](#architecture)
- [Daily operations, backups and upgrades](#maintenance)
- [Troubleshooting and recovery](#troubleshooting)
- [Repository layout and development checks](#development)
- [Repository history and documentation migration](#repository-history)
- [Dated validation evidence and outstanding integration work](#validation)

<a id="architecture"></a>
## Architecture and application compatibility

Jenkins is the controller: it schedules work, stores job settings and credentials,
and archives output. A node executes stages selected by its labels. In this starter,
Web/Android stages use the `built-in` node to drive Linux Docker containers; a native
Mac node labelled `flutter-macos` builds iOS. These labels are example saved job
settings, not defaults hardcoded into the Jenkinsfile. An iOS-only job can use an
existing reachable controller without a Linux build executor. `PLATFORM=all` needs
both execution environments.

| Controller topology | Workspace sharing | Host path |
| --- | --- | --- |
| Docker container named `jenkins` | `--volumes-from jenkins` | Linux or Windows/WSL Docker host |
| Jenkins running on the host | `-v "$WORKSPACE:$WORKSPACE"` | Native Mac controller driving Docker Desktop |

The pipeline tests for a container named `jenkins` on its selected Docker daemon.
If found, it inherits that container's volumes; otherwise it binds the workspace.
Avoid an unrelated container with that name in the native topology. Docker resolves
bind sources on its daemon's host. A label change alone does not provision a remote
worker or fix workspace sharing. The Docker context, paths and permissions must all
match. Host credential files outside the workspace receive individual read-only
mounts only when selected for Android release signing or Firebase/Google upload.

The initial checkout uses `workspace/ci-platform` for central tooling and
`workspace/app` for the Flutter source. These are disposable directories. App polling
is enabled on its first checkout; later platforms use the recorded `APP_COMMIT` and
`CI_COMMIT` so one run uses the same application and tooling revisions on Linux/Mac.
The Jenkinsfile exports saved job values explicitly, including for unattended builds,
and does not declare/overwrite job parameters.

Only the disposable native checkout is adapted. Android launcher labels, iOS display
names and Web document/PWA metadata use `APP_NAME`. The runners pass `ENVIRONMENT`,
`APP_NAME` and `API_BASE_URL` as Dart defines; existing Dart code must consume these
for in-screen title/API changes. Report hardcoded app incompatibility instead of
editing the application. Dependencies, plugins, namespace/source packages, schemes
and app business logic are preserved.

Standard Flutter Android app modules and iOS Runner layouts are supported. Existing
Android flavors/shared iOS schemes may be selected; they are not created by CI.
Multiple Android flavor dimensions, custom targets/extensions, localized display
names, generated/xcconfig-only plists and unusual layouts require a reviewed adapter
here in the central repository. Never install Jenkinsfiles, environment/signing files,
Gemfiles, Fastlane files or Dart configuration helpers into an app, or commit/push
app changes as setup.

Android project signing preserves existing app signing, potentially a debug key.
Jenkins signing binds a keystore plus three secret texts for release only. Bound
iOS signing uses a P12/password and explicit profile matching team, bundle ID and
profile Name; temporary keychains, search-list/profile changes are serialized and
cleaned up. Existing-keychain mode requires already usable host signing assets.
See [signing settings](CONFIGURATION.md) for the exact conditions.

The pipeline archives verified artifacts under
`app/build/ci/<environment>/<mode>/<platform>`. `SUCCESS` must contain exactly
`<environment> <mode> <platform>\n`. [Configuration](CONFIGURATION.md) lists the artifact
matrix and upload behavior. Uploads run after archive success; an upload failure fails
the job but retains its archived output. Fastlane Supply/Pilot and the Firebase App Distribution plugin are
central dependencies; no app Fastfile is executed.

<a id="maintenance"></a>
## Daily operations, backups and upgrades

For Compose, the default project name `flutter-cicd` uses volume
`flutter-cicd_jenkins_home`. It holds jobs, config, credentials, workspaces and archived
artifacts. A different Compose project or fresh-bootstrap override may use a different
volume and make Jenkins appear empty. Use the same files, project name and override
that created your controller for every operation below. Inspect existing volume
identity before changing anything.

```bash
docker compose -f host/compose.yaml stop jenkins
docker compose -f host/compose.yaml start jenkins
docker compose -f host/compose.yaml logs --tail=100 jenkins
docker system df
```

`stop`/`start` preserve state. `docker compose down --volumes` deletes named Jenkins
state; never use it for routine restart. Avoid broad Docker pruning. Configure job
build retention so artifacts do not fill storage. Docker Desktop must be running
on Windows/Mac, with suitable sleep/restart settings; the Windows recipe does not
install an unattended Windows service.

On the Mac, the example controller and agent services can be inspected, restarted,
or stopped with these commands. Finish running builds before restarting services.

```bash
launchctl print "gui/$(id -u)/local.flutter-ci.jenkins" | grep state
launchctl print "gui/$(id -u)/local.flutter-ci.flutter-mac-01" | grep state
launchctl kickstart -k "gui/$(id -u)/local.flutter-ci.jenkins"
launchctl kickstart -k "gui/$(id -u)/local.flutter-ci.flutter-mac-01"
tail -f ~/Library/Logs/local.flutter-ci.jenkins/stderr.log
# Run a separate tail or stop the first with Ctrl-C:
tail -f ~/Library/Logs/local.flutter-ci.flutter-mac-01/stderr.log
# Stop the controller until the next login or explicit bootstrap:
launchctl bootout "gui/$(id -u)/local.flutter-ci.jenkins"
```

LaunchAgents start at user login, persist after terminal close, and stop on logout.
They do not provide startup before login; that requires a separately configured
LaunchDaemon under a dedicated CI user. Keep the repository in a stable path such as
`~/ci/flutter-cicd-central`, outside Desktop/Documents/Downloads. The agent installer
captures the launcher path and shell PATH; reinstall it after moving that path or
changing the required tool locations.

### Consistent, protected backups

Quiet Jenkins and other build automation, wait for running jobs, and stop the
controller before archiving. Backups contain credentials: use restricted storage and
verify the archive succeeded before treating the backup as complete. Dependency
caches can be regenerated; Jenkins home is irreplaceable state.

Default Compose installation, from the repository root (use the actual volume for a
custom/bootstrap installation):

```bash
umask 077
mkdir -p "$HOME/ci/backups"
docker compose -f host/compose.yaml stop jenkins
docker run --rm -v flutter-cicd_jenkins_home:/data:ro \
  --mount "type=bind,source=$HOME/ci/backups,target=/backup" ubuntu:24.04 \
  tar -C /data -czf "/backup/jenkins-home-$(date +%Y%m%d-%H%M%S).tar.gz" .
# Check the tar command's exit status and inspect the saved archive before continuing.
docker compose -f host/compose.yaml start jenkins
```

Native Mac installation (match `JENKINS_HOME` from your controller service):

```bash
umask 077
launchctl bootout "gui/$(id -u)/local.flutter-ci.jenkins"
tar -czf ~/ci/jenkins-home-$(date +%Y%m%d-%H%M%S).tar.gz -C ~/ci/jenkins jenkins_home
# Check the archive command succeeded.
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/local.flutter-ci.jenkins.plist
```

Retain any bootstrap state directory and its Compose override for future restarts;
the configuration still references those bind-mounted files. Resume scheduling only
when the controller, agents and dependencies are ready.

### Upgrades and Mac performance

Back up state, select a reviewed Jenkins base image/plugin set, rebuild and test
separately before recreating a production service. Changing `host/jenkins/plugins.txt`
does not reliably downgrade/overwrite plugins already installed in an existing home;
treat changes as a plugin migration. Changing `host/.env` does not change an existing
Flutter image: rebuild it, verify its version, and align native Mac Flutter.

The earlier Mac setup guide reported these timings on an M-series Mac with 10 cores,
16 GB RAM and Docker limited to 7.7 GB: iOS debug about 2-3 minutes, Web debug about
1 minute 20 seconds, Android debug with a cold Gradle cache about 6 minutes 40 seconds.
These are reported setup observations, not reproduced integration evidence for this
revision or performance guarantees. Android/Web run amd64 Linux under emulation on
Apple Silicon (Rosetta when configured); iOS runs natively. Warm caches can improve
times. Keep heavy builds serialized and raise Docker memory if actual OOM evidence
appears. The native Mac topology is documented, but live Mac/Xcode/signing and upload
validation remain pending in the record below.

<a id="troubleshooting"></a>
## Troubleshooting and recovery

### Where to look first

| What | Command |
| --- | --- |
| Jenkins log (containerised) | `docker compose -f host/compose.yaml logs --tail=200 jenkins` |
| Jenkins log (macOS service) | `tail -50 ~/Library/Logs/local.flutter-ci.jenkins/stderr.log` |
| Mac agent log | `tail -50 ~/Library/Logs/local.flutter-ci.flutter-mac-01/stderr.log` |
| Build console | Jenkins → job → build number → **Console Output** |
| Node status | Jenkins → **Manage Jenkins → Nodes** |

**Read the exit code.** It narrows the cause quickly:

| Exit code | Meaning |
| --- | --- |
| `125` | Docker daemon rejected the run — volume/mount/image problem, container never started |
| `126` | Command found but not executable; inspect permissions and, on macOS, TCC access |
| `127` | Command not found — `PATH` problem |
| `137` | Process received SIGKILL; check memory evidence for OOM or another forced termination |

### Preflight and prerequisites

#### `This starter requires an amd64 Docker host; found aarch64`

**Cause:** `host/check-host.sh` on Apple Silicon or ARM Linux.

**Fix:** On macOS, this is expected — that script validates the containerised topology
which the macOS path does not use. Skip it and follow
[native Mac setup](SETUP_MACOS.md#macos), which runs the container as emulated amd64 with
a host-based controller. The packaged Linux/WSL preflight requires x86-64; ARM Linux is not a documented setup path.

#### `ERROR: Python 3.10+ is required.`

**Cause:** The selected `python3` is older than 3.10. Check the actual interpreter; installed versions vary by host.

**Fix:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12 --default
python3 --version
```
Ensure `~/.local/bin` precedes `/usr/bin` on your login `PATH`, then **reinstall any
LaunchAgent installed before this change** — it captured the old `PATH`.

#### `Expected Flutter 3.47.0; found 3.47.1.`

**Cause:** `host/macos/check-host.sh` requires an **exact** match with its argument.

**Fix:** Pass your installed version: `bash host/macos/check-host.sh 3.47.1`. Also set
`FLUTTER_VERSION` in `host/.env` to the same value, rebuild the selected image, and verify `docker run --rm flutter-ci:1.0 flutter --version`. Updating `.env` alone does not update an image. Pass the version selected for this app to preflight; do not merely bypass a required version mismatch.

#### `Missing prerequisite: <tool>`

**Fix:** Install it and make sure it's on the `PATH` of the shell running the check.
Common: `bundle` (`gem install bundler -v 4.0.20`), `pod` (`gem install cocoapods`).

#### `Complete Xcode license acceptance` / `first-launch setup`

```bash
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
```

#### Bundler version conflicts

**Cause:** Both `scripts/ios/Gemfile.lock` and `scripts/upload/Gemfile.lock` pin `BUNDLED WITH 4.0.20`, and uploads run with
`BUNDLE_FROZEN=true`.

**Fix:** `gem install bundler -v 4.0.20`

### Jenkins controller

#### Jenkins looks empty after moving to a service — jobs gone

**Cause:** `JENKINS_HOME` isn't set, so Jenkins used `~/.jenkins`. Check the old home and its backups before concluding that data was lost; a different home may simply be in use.

**Check:**
```bash
python3 -c "import os,plistlib; p=os.path.expanduser('~/Library/LaunchAgents/local.flutter-ci.jenkins.plist'); print(plistlib.load(open(p,'rb'))['EnvironmentVariables']['JENKINS_HOME'])"
```

**Fix:** Add `JENKINS_HOME` to the service's `EnvironmentVariables` (macOS plist) or the
container environment, then restart.

#### Port 8080 already in use

```bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
```
Identify the listener before stopping an owned conflicting service, or change `JENKINS_HTTP_PORT` in `.env` (containerised) /
`--httpPort` (macOS).

#### `Container 'jenkins' already exists` from `check-host.sh`

**Cause:** An existing installation. The preflight refuses to run over it.

**Fix:** Keep the existing installation and plan a migration. `--allow-existing` is
diagnostics only — it is **not** a migration command.

#### Jenkins doesn't start after reboot (macOS)

**Expected.** LaunchAgents start at **login**, not at boot. Log in and they start.
Unattended-before-login needs a system `LaunchDaemon` under a dedicated CI user.

#### Editing `config.xml` by hand has no effect

**Cause:** Jenkins holds configuration in memory and rewrites files on shutdown.

**Fix:** Prefer the Jenkins UI or the owned-job helper. For a necessary offline edit, wait for builds to finish, back up the configuration, stop Jenkins, edit, then start.
```bash
launchctl bootout "gui/$(id -u)/local.flutter-ci.jenkins"
# edit
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/local.flutter-ci.jenkins.plist
```

### Agent connection

#### Agent service fails instantly, exit code 126, `Operation not permitted`

```
/bin/bash: /Users/you/Desktop/.../start-agent.sh: Operation not permitted
```

**Cause:** macOS TCC blocks background services from reading `~/Desktop`, `~/Documents`
and `~/Downloads`. Interactive shells have access; `launchd` services do not.

**Fix:** Wait for this agent's builds to finish, stop its owned service, copy the repository to an unused stable path and reinstall from a shell with the required tools. Replace the source path and connection settings below with your actual values:
```bash
launchctl bootout "gui/$(id -u)/local.flutter-ci.flutter-mac-01"
mkdir -p ~/ci &&
test ! -e ~/ci/flutter-cicd-central &&
cp -R ~/Desktop/projects/flutter_cicd_central ~/ci/flutter-cicd-central &&
bash ~/ci/flutter-cicd-central/host/macos/install-agent.sh \
  "http://127.0.0.1:8080" "flutter-mac-01" \
  "$HOME/.config/flutter-ci/agent.secret" "$HOME/jenkins-agent"
```

#### Agent connects interactively but the service stays offline

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

#### `ERROR: Secret must be readable, nonempty, owned by this user and mode 600.`

```bash
chmod 600 ~/.config/flutter-ci/agent.secret
ls -l ~/.config/flutter-ci/agent.secret
```
It must be a **regular file** (not a symlink) and **outside** the agent work directory.

#### Agent rejected / immediately disconnects

**Cause:** Usually a WebSocket mismatch — `start-agent.sh` always passes `-webSocket`, so
the node must have it enabled.

**Check:**
```bash
grep webSocket ~/ci/jenkins/jenkins_home/nodes/flutter-mac-01/config.xml
```
Must be `<webSocket>true</webSocket>`. Prefer enabling **Use WebSocket** in the node Configure page. If an offline XML correction is necessary, follow the backed-up/stopped-controller procedure in [Mac agent setup](SETUP_MACOS.md#mac-agent). Also confirm the secret matches the node currently in Jenkins — deleting and
recreating a node generates a **new** secret.

#### `Use a new secret file; existing files and symlinks are never replaced.`

**Cause:** `macos_agent.py` refuses to overwrite.

**Fix:** Choose a new protected path and update the launcher after verifying the new secret. Keep any secret still used by another node/service; the helper deliberately does not overwrite it.

### Docker and volumes

#### `failed to mkdir /var/lib/docker/volumes/flutter-pub-cache/_data/hosted: file exists`

Build fails with **exit code 125** before the container starts.

**Cause:** Docker copies image content into an **empty** named volume on first mount.
The image's `/root/.pub-cache` is populated by `flutter precache`, and that copy fails on
Docker Desktop with the containerd image store enabled.

**Fix: rebuild the shared package cache during a maintenance window:**

1. Put Jenkins into **Prepare for Shutdown** (quiet-down mode) to prevent new
   builds from starting, and pause any other automation using `flutter-pub-cache`.
   Wait for all running builds and other cache users to finish. Keep them paused
   throughout this procedure; do not stop running build containers to free the cache.
2. List every container referencing the cache. This command only inspects them:

   ```bash
   docker ps -a --filter "volume=flutter-pub-cache" \
     --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}'
   ```

   If a running container appears, wait for its work to finish. For each remaining
   container, verify that it belongs to a completed/failed CI build and is no longer
   needed. Remove only an individually identified, stopped stale container, replacing
   `STALE_CONTAINER_ID` below with its exact ID:

   ```bash
   docker inspect --format '{{.Name}} {{.State.Status}}' STALE_CONTAINER_ID
   docker rm STALE_CONTAINER_ID
   ```

   Run inspection first and review its output before removal. Do not add `--force`,
   remove unrelated containers, or pipe the container list into a removal command.
   If a container's ownership is unclear, stop this recovery procedure and check
   with its owner. Repeat the read-only listing and proceed only when it is empty.
3. The following resets **only the shared package cache**; packages will be
   downloaded again as needed. Run the entire command block together. Each step
   runs only if the previous step succeeds:

   ```bash
   docker volume rm flutter-pub-cache &&
   docker volume create flutter-pub-cache &&
   docker run --rm \
     --mount type=volume,src=flutter-pub-cache,dst=/mnt,volume-nocopy \
     --entrypoint sh flutter-ci:1.0 \
     -c 'cp -a /root/.pub-cache/. /mnt/' &&
   docker run --rm \
     --mount type=volume,src=flutter-pub-cache,dst=/root/.pub-cache,volume-nocopy \
     --entrypoint sh flutter-ci:1.0 \
     -c 'test -n "$(ls -A /root/.pub-cache)"'
   ```

   `docker volume rm` reports an error and exits nonzero when a container still
   references the volume, including a stopped container. The `&&` chain prevents
   recreation or population after that failure. If any step fails, keep builds
   paused and investigate the reported error; do not run later steps separately
   or treat a partially populated cache as repaired. `volume-nocopy` disables the
   image-to-volume copy that caused the original startup failure.
4. Once the full block succeeds, cancel Jenkins's quiet-down mode and resume the
   other paused automation. Retry one failed build to verify recovery.

#### Build container sees an empty workspace

**Cause:** Wrong mount strategy for your controller topology. `docker run -v /p:/p`
resolves the source on the **Docker host**; a containerised Jenkins keeps its workspace
in a named volume that doesn't exist at that host path, so Docker creates an empty
directory.

**Fix:** The pipeline auto-detects this via `ci_docker_run()` in the `Jenkinsfile`:

- container named `jenkins` exists → `--volumes-from jenkins`
- otherwise → `-v "$WORKSPACE:$WORKSPACE"`

If you changed this, restore it. Note the containerised controller **must** be named
exactly `jenkins`.

#### `docker: command not found` in a build step

**Cause:** `docker` isn't on the Jenkins process `PATH`.

**Fix (macOS):** Locate the installed Docker CLI with `command -v docker` (often `/usr/local/bin/docker`, depending on Desktop settings). Reinstall the Jenkins
LaunchAgent from a shell whose `PATH` includes it.
**Fix (containerised):** The `jenkins` image bundles the Docker CLI; verify the socket
mount with `docker exec jenkins docker version`.

#### `Cannot connect to the Docker daemon`

- Docker Desktop running?
- `/var/run/docker.sock` mounted into the Jenkins container?
- On WSL2, is Docker Desktop's Ubuntu integration enabled?

#### `docker compose down --volumes` deleted everything

**Cause:** That flag removes named volumes, including `flutter-cicd_jenkins_home`.

**Prevention:** Use the stop/start commands in [maintenance](#maintenance), with the same Compose files/project/override used at setup. Take regular protected backups.

### Build failures

#### Build queues forever, never starts

**Cause:** No online node carries the requested label.

**Check:** Compare **Manage Jenkins → Nodes** labels against the job's
`LINUX_AGENT_LABEL` / `MACOS_AGENT_LABEL`. They must match **exactly** — the node's
*name* is irrelevant.

Also: `MACOS_AGENT_LABEL` cannot be `built-in` or `master` when `PLATFORM` is `ios` or
`all`; validation rejects it.

#### `OutOfMemoryError` / `Killed` / exit 137 during Gradle

**Cause:** OOM is one possible reason for a killed Gradle process; verify Docker/host memory evidence and rule out another forced stop.

**Fix:** Keep the built-in node at **1 executor** and serialize heavy builds. If memory is exhausted, raise Docker memory in Settings > Resources within the host budget (the previous guide suggested 10-12 GB), leaving room for macOS/Xcode, or close other heavy applications.

#### `NDK not configured` / missing NDK

```bash
docker run --rm -v flutter-ndk-cache:/opt/android-sdk/ndk \
  flutter-ci:1.0 sdkmanager "ndk;<version-your-app-needs>"
```
The image does not bake the NDK; the named volume holds it.

#### Android build extremely slow on Apple Silicon

The amd64 Linux image runs under emulation on Apple Silicon (Rosetta when configured in Docker Desktop). The earlier Mac guide reported about 6-7 minutes cold; this depends on app, host and caches and is not an acceptance target. A dedicated x86-64 Linux host avoids this emulation.

#### `Missing success marker for <platform>`

**Cause:** The build script didn't complete, so the `SUCCESS` marker was never written.

**Fix:** Scroll **up** in the console output — the real error is above this line. This
message is a symptom, not the cause.

#### `Built iOS bundle ID/display name does not match the selected environment`

**Cause:** `IOS_BUNDLE_ID` or `APP_NAME` doesn't match what the Xcode project produced.

**Fix:** Inspect the adapted disposable checkout and built artifact: `PRODUCT_BUNDLE_IDENTIFIER` should equal the selected `IOS_BUNDLE_ID`. The central adapter applies this override; the original app may use another ID. Confirm that
`IOS_SCHEME` names a **shared** scheme (`ios/Runner.xcodeproj/xcshareddata/xcschemes/`).
Remember `IOS_BUNDLE_ID` forbids underscores.

#### `This project requires CocoaPods`

The app has an `ios/Podfile`. Install CocoaPods on the Mac agent (`gem install
cocoapods`) and make sure `pod` is on the **service** `PATH`, then reinstall the agent.

#### App checkout fails / authentication error

- Private repo → set `APP_CREDENTIALS_ID` to a valid Jenkins credential ID
- `APP_BRANCH` must be a **branch**, not a tag or PR ref
- Verify the URL is reachable from the build machine

### Signing and uploads

#### `Configure ANDROID_KEYSTORE_CREDENTIAL_ID` (or similar)

Android release with `ANDROID_RELEASE_SIGNING=jenkins` requires **all four** credential
IDs. With `project` signing they must **all be empty**.

#### `An iOS release requires IOS_TEAM_ID`

Set the 10-character uppercase Team ID. Manual signing also needs `IOS_PROFILE_NAME`;
`jenkins` signing needs all three iOS credential IDs **and** `IOS_SIGNING_STYLE=manual`.

#### `Existing-keychain signing uses empty Jenkins certificate/password/profile credential IDs`

Mutually exclusive settings. Either use `existing-keychain` with empty IDs, or `jenkins`
with all three set.

#### `Use an explicit provisioning profile for this environment's bundle ID`

The profile's team + app ID must equal `IOS_TEAM_ID` + `IOS_BUNDLE_ID`. Wildcard or
mismatched profiles are rejected.

#### `Google Play upload requires an Android release AAB`

Play requires `BUILD_MODE=release` and `ANDROID_ARTIFACT_TYPE=aab`. APKs and debug builds are rejected.

#### `iOS uploads require a signed release IPA; simulator builds cannot be uploaded`

Set `BUILD_MODE=release` with signing configured. Debug iOS produces a simulator archive.

#### `App Store Connect upload requires IOS_EXPORT_METHOD=app-store-connect`

Firebase iOS uploads instead need `release-testing`, `debugging` or `enterprise`.

#### `FIREBASE_ANDROID_APP_ID must be a Firebase Android app ID`

Format: `1:<digits>:android:<alphanumeric>` (or `:ios:`). Copy it from the Firebase
console. `FIREBASE_GROUPS` must be comma-separated aliases with **no spaces**.

### Automation helper

#### `Confirm the collected settings before use: schema_version=1, confirmed=true.`

Review the actual public settings, then set `"schema_version": 1` and `"confirmed": true` in `answers.json`. Do not confirm placeholder values.

#### `project_id` / `job_name` rejected

`project_id` must match `[A-Za-z][A-Za-z0-9_.-]{0,79}`: start with a letter and use no spaces. `job_name` also permits internal spaces, for example `Android Staging Release`, and must match `[A-Za-z][A-Za-z0-9 ._-]{0,79}` without leading/trailing spaces. Both are limited to 80 characters; job folder paths are unsupported.

#### `Provide JENKINS_USER and JENKINS_API_TOKEN through the protected process environment.`

```bash
export JENKINS_USER=admin
read -s JENKINS_API_TOKEN && export JENKINS_API_TOKEN
```
Create the token at **your username → Security → API Token**.

#### Git: `Author identity unknown`

```bash
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"
```

#### Git: `could not read Username for 'https://github.com'`

Non-interactive shell can't prompt. Push from your own terminal, or configure `gh auth
login` / an SSH remote. GitHub HTTPS needs a **Personal Access Token**, not your account
password.

### Harmless warnings

These messages have appeared in successful builds. Check the surrounding output and final result before treating a warning as harmless:

| Message | Explanation |
| --- | --- |
| `WARNING: The requested image's platform (linux/amd64) does not match the detected host platform` | Expected on ARM — the image runs translated. |
| `Couldn't poll for events, error = 4` / `NativeException ... executeRunLoop0` | Gradle's native file-watching can't work through a virtualised filesystem. If Gradle falls back and compilation succeeds, no recovery is needed for this warning alone. |
| `This version only understands SDK XML versions up to 3 but ... version 4 was encountered` | cmdline-tools slightly older than SDK metadata. Check installed tool/metadata versions if SDK operations also fail. |
| `The SDK Manager CLI tool (sdkmanager) is deprecated` | Still functional. |
| `N packages have newer versions incompatible with dependency constraints` | Normal `pub` output. |
| `Selected Git installation does not exist. Using Default` | Jenkins falls back to `git` on `PATH`. Fine. |

### Recovery

#### Reset a single job's workspace

Pause this job and wait for all its builds to finish. Confirm its node and exact disposable workspace under the actual Jenkins home, preserve any unarchived output you need, then use the job\'s **Workspace > Wipe Out Current Workspace** action when available. Otherwise remove only that verified disposable directory using the host file manager. Never select the app source repository or Jenkins home itself. The next build re-clones both repositories.

#### Rebuild all caches from scratch

Use the package-cache procedure above for `flutter-pub-cache`. For `gradle-cache`, `flutter-ndk-cache` or `flutter-upload-gems`, quiet Jenkins and all other consumers, wait for active work, and inspect references to each exact volume. Remove individually identified stopped stale containers only, then reset only the affected cache. Re-provision and verify the NDK as in your host guide: [Windows/WSL](SETUP_WINDOWS_WSL.md#linux-image), [Linux](SETUP_LINUX.md#linux-image) or [Mac](SETUP_MACOS.md#caches); Gradle and upload gems refill on the next applicable run. Keep builds paused until provisioning succeeds. Caches are derived data, but deleting them while consumers run can corrupt a build; never include the Jenkins home volume.

#### Rebuild the image

```bash
docker compose -f host/compose.yaml --profile tools build --no-cache flutter-ci
```

#### Full restart

```bash
# containerised
docker compose -f host/compose.yaml stop jenkins && docker compose -f host/compose.yaml start jenkins

# macOS
launchctl kickstart -k "gui/$(id -u)/local.flutter-ci.jenkins"
launchctl kickstart -k "gui/$(id -u)/local.flutter-ci.flutter-mac-01"
```

#### Verify the whole chain

| Check | Command |
| --- | --- |
| Jenkins responds | `curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/login` |
| Configured Jenkins home (also check the active service) | `plutil -p ~/Library/LaunchAgents/local.flutter-ci.jenkins.plist` |
| Image present | `docker image inspect flutter-ci:1.0 --format '{{.Architecture}}'` |
| Toolchain works | `docker run --rm flutter-ci:1.0 flutter --version` |
| Caches populated | `docker run --rm --mount type=volume,src=flutter-pub-cache,dst=/c,readonly,volume-nocopy --entrypoint sh flutter-ci:1.0 -c 'ls -A /c'` |
| Agent service running (confirm online in Jenkins Nodes too) | `launchctl print "gui/$(id -u)/local.flutter-ci.flutter-mac-01" \| grep state` |
| Xcode selected | `xcode-select -p` |

#### `CI_PLATFORM: parameter not set`

Jenkins removes environment variables assigned empty values. Older central revision
`refs/tags/v1.0.0` used an unguarded optional `CI_PLATFORM` during validation. The
current wrapper uses `${CI_PLATFORM:-}`. Select a central tooling revision containing
that fix and rebuild; see the dated evidence below. A successful app checkout alone
does not establish that the build image ran.

#### Host signing or upload credential file is missing in Docker

A host-based Jenkins secret file can live outside `$WORKSPACE`. The current pipeline
mounts only the selected Android release keystore or Firebase/Google JSON file,
read-only at its original absolute path. Check that the selected Jenkins credential
ID resolves to the correct type and the bound file is readable on the Docker host.
Do not copy credentials into the checkout or mount the whole temporary directory.
Containerized Jenkins uses its inherited volumes; validate/quality/debug/project
signing and dependency installation do not add credential mounts.

<a id="development"></a>
## Repository layout and development checks

| Location | Responsibility |
| --- | --- |
| `Jenkinsfile` | Stable Pipeline SCM entrypoint: checkouts, routing, credential binding and archives |
| `scripts/build.py`, `scripts/build-ios.py` | Validation/quality and platform runners; iOS dispatch/signing/cleanup |
| `scripts/android/override.gradle` | Temporary Android ID/suffix override and Jenkins release signing |
| `scripts/ios/prepare.rb`, `scripts/ios/Gemfile`, `scripts/ios/Gemfile.lock` | Disposable Runner project/plist adaptation and locked xcodeproj/REXML dependencies |
| `scripts/upload.py`, `scripts/upload_settings.py` | Artifact uploads and shared runtime/setup validation/defaults |
| `scripts/upload/` | Separate locked Fastlane bundle and direct Firebase/Supply/Pilot runner |
| `automation/scripts/setup.py` | Public answers validation, job XML, owned-job create/update/backups, build/queue/status APIs |
| `automation/scripts/macos_agent.py` | Owned Mac node creation/verification and protected inbound secret file |
| `automation/assets/bootstrap.groovy` | Secured initialization of an explicitly marked fresh empty Jenkins home |
| `automation/answers.example.json` | Complete public input template, initially unconfirmed |
| `host/` | Shared Compose, Dockerfiles, pinned plugins and Linux/WSL preflight |
| `host/macos/` | Native preflight and stable Mac agent launcher/installer paths |
| `tests/` | All portable build/native/upload/pipeline/credential and setup/node tests |
| `documents/` | Three host setup guides, plus shared configuration and operations |
| `requirements/` | Unmodified original PDF and derived requirements handover |
| `FILES.csv` | Repository deliverable hashes, excluding itself and generated/private state |
| `manifests/host.csv`, `manifests/requirements.csv` | Host-relative inventory and root-relative immutable requirements hashes |

Start changes by reading [AGENTS.md](../AGENTS.md), this guide and the
[configuration contract](CONFIGURATION.md). Inspect current Git status and code;
historical handover entries do not prove current host health. Preserve unrelated
changes and existing Jenkins services/jobs. Coordinate exclusive file/service
ownership if using multiple agents. Serialize memory-heavy Gradle checks and builds
sharing a checkout.

From the central repository, using Python 3.10+ (`python` on Windows):

```bash
python3 -B -m unittest discover -s tests -p 'test_*.py'
# Focused runner/native/setup checks when appropriate:
python3 -B -m unittest discover -s tests -p 'test_build.py'
python3 -B -m unittest discover -s tests -p 'test_native.py'
python3 -B -m unittest discover -s tests -p 'test_setup.py'
python3 -B -m unittest discover -s tests -p 'test_macos_agent.py'
# Real locked Firebase plugin options; publishing is stubbed:
BUNDLE_GEMFILE="$PWD/scripts/upload/Gemfile" BUNDLE_FROZEN=true \
  bundle exec ruby tests/test_upload_firebase.rb
# Jenkins steps stubbed; requires Groovy:
groovy tests/test_upload_pipeline.groovy
git diff --check
```

`-B` or `PYTHONDONTWRITEBYTECODE=1` avoids bytecode changing an inventory check.
Native tests use tool stubs and may print fixture artifact paths. Groovy parsing
checks language syntax; neither it nor stub tests proves Jenkins Declarative,
Android/iOS compilation/signing or upload integration.

For configuration/behavior changes, check Jenkinsfile, setup validator/renderer,
shared upload settings, native runners and public example together. Keep the 42
parameter reference aligned with `automation/scripts/setup.py` and runtime validation.
For documentation/path changes, check local links and anchors, parameter coverage,
script/bundle references and manifests. Run real builds only when relevant to the
change, and record actual evidence/date below. Use the [helper workflow](CONFIGURATION.md#automation)
to validate/render answers outside repositories before authorized live changes.

After changing deliverables, refresh host hashes and then `FILES.csv`; preserve the
requirements manifest's original hashes. Include new/moved deliverables, exclude
removed files, `.git`, local answers/XML, credentials, backups and build/cache output.
`manifests/host.csv` paths resolve under `host/`; both other manifests use repository
root paths. Verify recorded bytes from the root:

```bash
python3 -B - <<'PY'
import csv, hashlib
from pathlib import Path
root = Path.cwd()
for manifest, base in [("FILES.csv", root), ("manifests/host.csv", root / "host"),
                       ("manifests/requirements.csv", root)]:
    rows = list(csv.DictReader((root / manifest).open(encoding="utf-8-sig", newline="")))
    assert len({row["Path"] for row in rows}) == len(rows), manifest
    for row in rows:
        path = base / row["Path"]
        assert path.is_file(), path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["SHA256"], path
    print(f"{manifest}: {len(rows)} hashes verified")
PY
```

<a id="repository-history"></a>
## Repository history and documentation migration

The central repository was imported at `D:/Projects/GIT/flutter-cicd-central` on
branch `main`, initial import commit `daa5e26`. On 2026-09-08 the user reported
creating/pushing it. Development began under `D:/Projects/GIT/ci_cd_test`; those older
distribution copies are historical and must not be edited unless the user requests
a new distribution. The former distribution skill coordinated intake, host setup and
verification; the standalone repository now contains the working helpers and guides.

An earlier branch-rule/Multibranch approach was rejected and undone. The accepted
model is a regular Pipeline per app/branch/configuration, copyable with independently
saved settings. Central SCM and app SCM stay distinct. Job parameters own public app
configuration; no central environment file is installed/read from an app.

The original [requirements PDF](../requirements/Flutter%20CI-CD.pdf) and
[derived handover](../requirements/FLUTTER_CICD_AGENT_HANDOVER.md) remain byte-for-byte
unchanged and retain their hashes. They describe broader production plans and an older
app-side architecture. Later accepted zero-app-files/job-owned settings govern this
implementation. On 2026-09-08 the user explicitly added per-job automatic uploads,
superseding the earlier exclusion of Firebase distribution settings. Web deployment,
feature flags and other broader historical requirements remain future scope.

The older `CI_CD` job lived on a separate existing Jenkins controller; its current
status/settings have not been established by these records. Publishing this repository
does not migrate/configure that job. Temporary historical containers
`flutter-central-runner-validation` and an anonymous optional native Gradle fixture
may need inspection after the recorded Docker failure; verify identity/ownership
before cleanup, without restarting shared services or removing unrelated resources.

The 2026-09-09 consolidation replaces the previous scattered guides as follows. Old
filenames here are migration references, not maintained document links:

| Previous document(s) | Current home for their information |
| --- | --- |
| Root `README.md`, `documents/README.md` | [README](../README.md), architecture above and setup prerequisites |
| `HOST_SETUP.md`, `IOS_SETUP.md`, `host/README.md`, `host/macos/README.md` | [Windows/WSL setup](SETUP_WINDOWS_WSL.md), [Linux setup](SETUP_LINUX.md) and [Mac setup](SETUP_MACOS.md); maintenance/troubleshooting here |
| `documents/01-setup-windows-wsl.md`, `02-setup-linux.md`, `03-setup-macos.md` | [Windows/WSL setup](SETUP_WINDOWS_WSL.md), [Linux setup](SETUP_LINUX.md) and [Mac setup](SETUP_MACOS.md); job creation in [CONFIGURATION](CONFIGURATION.md); maintenance, reported timings and limits here |
| `automation/assets/BOOTSTRAP.md` | [Windows/WSL bootstrap](SETUP_WINDOWS_WSL.md#fresh-bootstrap) or [Linux bootstrap](SETUP_LINUX.md#fresh-bootstrap) |
| `JENKINS_SETUP.md`, `AUTOMATION.md` | [CONFIGURATION](CONFIGURATION.md), with bootstrap/node setup in the respective host guides |
| `PARAMETERS.md`, `documents/04-parameters.md`, `UPLOADS.md` | [CONFIGURATION](CONFIGURATION.md), including all parameters, credential types, upload prerequisites and examples |
| `documents/05-troubleshooting.md` | Troubleshooting and recovery here |
| `AGENT_HANDOVER.md`, `VALIDATION.md` | Architecture, development, history and dated validation here |

The combined `documents/SETUP.md` was subsequently split at the user's request into `SETUP_WINDOWS_WSL.md`, `SETUP_LINUX.md` and `SETUP_MACOS.md`. Each host guide contains its applicable complete setup steps, while configuration and operations stay shared.

Runtime/script migration:

| Previous path | Current path |
| --- | --- |
| `scripts/android.gradle` | `scripts/android/override.gradle` |
| `scripts/prepare-ios.rb` | `scripts/ios/prepare.rb` |
| Root `Gemfile`, `Gemfile.lock` | `scripts/ios/Gemfile`, `scripts/ios/Gemfile.lock` |
| `upload/Gemfile`, `upload/Gemfile.lock`, `upload/run.rb` | Same filenames under `scripts/upload/` |
| `automation/scripts/test_*.py` | Same test filenames under `tests/` |
| `HOST_MANIFEST.csv`, `REQUIREMENTS_MANIFEST.csv` | `manifests/host.csv`, `manifests/requirements.csv` |

The Jenkinsfile, public Python entrypoints, automation commands and deployed Mac host
launcher paths remain stable. Pipeline/runners now select the relocated bundles.
For manual Ruby commands, set `BUNDLE_GEMFILE="$PWD/scripts/ios/Gemfile"` for native
adaptation or `BUNDLE_GEMFILE="$PWD/scripts/upload/Gemfile"` for upload dependencies.
Apply the new central revision as a whole; do not combine an old Jenkinsfile with
new support-file locations. Documentation/file organization does not itself publish a
revision or update live jobs.

<a id="validation"></a>
## Dated validation evidence

Historical results below describe their dated revisions, not current host health.
Original commands are updated where files moved; counts still describe the original
runs. No current setup/integration result should be inferred from these records.

Local checks on 2026-09-07:
- 11 build-runner contract tests passed.
- 16 automation tests passed: settings, separate CI/app repositories, saved job values, ownership/backups, pinned refs and Mac secret handling.
- 12 native tests passed on Linux. Windows passed 11 with one POSIX-only skip. Native tests use tool stubs; they are not real signed builds.
- Ruby syntax and a real xcodeproj operation on a disposable project copy passed, changing the iOS name/ID without touching the original.
- The central Jenkinsfile compiled with Groovy 3.0.25 without executing it. This checks language syntax, not Jenkins Declarative/runtime behavior.
- A fresh Flutter 3.47 app without CI files passed formatting, analysis, widget tests and a real Web debug build with the parameterized name.
- Package manifests, unchanged original requirements and automatic.zip are verified during assembly.

### Outstanding integration checks

Docker Desktop's engine returned HTTP 500 during concurrent Android/Gradle checks. The Android APK build and flavored-Gradle check have no confirmed result. This central version has not completed Android release compilation or real Mac/Xcode compilation/signing.

The planned isolated Jenkins app-commit/polling and fresh-bootstrap integration tests could not run while Docker was unavailable. App checkout has polling enabled, but actual automatic-trigger execution remains to be verified. Historical per-project tests do not validate this new pipeline.

Temporary containers may need cleanup after Docker recovers: flutter-central-runner-validation and the anonymous optional native Gradle fixture. No shared Docker/Jenkins restart was attempted. No live jobs or credentials were changed.

### Target acceptance

Publish only the central repository and configure a fresh central job. Verify real selected-platform artifacts, exact native names/IDs and intended release signing. Run Jenkins once and verify archived artifacts and saved parameters. Then verify an authorized app update triggers the selected branch/job with those settings. Do not push a test change into an app without authorization.

For fresh hosts verify secured bootstrap and restart persistence; for iOS verify the native worker, compilation and signing cleanup. Confirm the app Git tree receives no CI/configuration commits.

The supplied Flutter test project's app files and root Jenkinsfile were unchanged during centralization. At the end of the 2026-09-07 validation session, central tooling was local and had not been connected to a live job.

### Repository move reported 2026-09-08

The user reports creating and pushing the standalone repository at D:/Projects/GIT/flutter-cicd-central. This supersedes the earlier local-only publication status. No new live Jenkins connection, host recovery or platform/trigger validation is implied by that move. See [repository history](#repository-history) for continuation context.

### Optional Linux platform variable fix: 2026-09-08

A user-supplied Jenkins console log shows central tag refs/tags/v1.0.0
(commit daa5e261ae27ca88bea5cb4dc6540a85c6ed3b7d) and the app branch checking
out successfully, followed by `CI_PLATFORM: parameter not set` in Validate
App Configuration, before Docker or Flutter execution. The log reports an SCM
trigger, but does not establish which repository change triggered it.

Jenkins withEnv removes variables assigned an empty value. The Linux wrapper
now uses `${CI_PLATFORM:-}` for the optional platform check under `set -eu`.
No public parameters, platform routing or native runners changed.

Local Windows verification with Git for Windows Bash:
- The new shell regression test reproduced failures for validate and quality
  with CI_PLATFORM absent before the fix.
- After the fix, 2 shell tests passed, covering absent/empty platform values,
  explicit web/Android arguments, workspace paths containing spaces and failure
  when required CI_ACTION is missing. The actual Jenkinsfile shell body runs;
  Docker is stubbed. Run with
  `python3 -B -m unittest discover -s tests -p 'test_pipeline.py'`.
- 11 build-runner and 16 setup automation tests passed.

These checks do not execute Jenkins or real platform builds. The correction
must be published and the job's central SCM ref updated from v1.0.0 to a fixed
revision before rerunning Jenkins. No live job, release tag or app was changed.

### Configurable artifact uploads: 2026-09-08

Implemented the user's per-job destination choices: Android none/firebase/google,
iOS none/firebase/appstore, Web none. Missing new settings preserve build-only
jobs. The setup renderer and runtime share upload validation. Upload stages run
after platform archival and bind only the selected publishing credential. The
appstore destination uploads to App Store Connect/TestFlight without App Review
submission. Google Play track/status are configurable, defaulting to internal/draft.

The native iOS runner previously wrote a generic SUCCESS marker that did not
match Jenkins archive checks. It now writes the same environment/mode/platform
marker as the other runners; the six native environment/mode cases assert it.

Verification on Windows and disposable Linux containers:
- Full central Python suite: 39 tests, 38 passed and one POSIX-only native signing
  test skipped on Windows. Includes 11 upload tests and 5 pipeline shell tests.
- Setup automation: 21 tests passed, including existing-answer migration,
  rendered upload settings and conditional upload requirements.
- Shell tests execute the actual Jenkinsfile wrapper with Docker stubbed, testing
  unset/empty optional values, workspace spaces, credential-name forwarding and
  nonzero Docker exit propagation.
- An isolated container parsed the complete Jenkinsfile using Groovy and passed
  six upload-helper stub cases: disabled uploads, provider credential selection,
  installation before credential binding and binding scope cleanup. This is not
  execution of a live Jenkins Pipeline or its Declarative engine.
- A disposable Linux container installed the separate locked upload bundle:
  Fastlane 2.239.0, Bundler 4.0.20, 101 gems. Ruby syntax and actual Fastlane
  Supply/Pilot configuration checks passed, including absent release notes.
  Service upload methods were stubbed, with no publishing operation.
- All 41 setup parameters are covered in the configuration reference; edited documentation
  relative links and repository manifests were checked. Original requirement
  files and their hashes remain unchanged.

Commands: `python3 -B -m unittest discover -s tests -p 'test_*.py'` and
`python3 -B -m unittest discover -s tests -p 'test_*.py'` (automation tests were moved into `tests/` on 2026-09-09).

No real Firebase App Distribution, Google Play or App Store Connect upload has
been performed. No Jenkins jobs, credentials, app repositories or release tags
were changed. Publishing this central revision, configuring the destination and
credentials, and verifying actual signed artifact acceptance remain required
for live deployment. Linux dependency checks do not prove native Mac/Xcode,
Apple Silicon bundle installation or Apple Transporter upload success.

### Host credential mounts and targeted cache recovery: 2026-09-08

Scope: fix host-run Jenkins credential visibility and the troubleshooting cache
cleanup procedure. No public parameter, upload destination, native iOS execution,
LaunchAgent or scheme behavior was changed.

The host branch of the Linux build/upload wrappers now bind-mounts only the
selected credential file, read-only at its existing absolute path. Android
Jenkins release signing selects the keystore; Firebase/Google Play upload selects
that provider's JSON. Validation, quality, debug/project signing and dependency
preparation add no credential mounts. The containerized branch retains its
existing --volumes-from jenkins behavior. Missing or non-file host bindings fail
before Docker starts. CSV escaping preserves spaces, commas and quotes in paths;
shell tracing is disabled before reading bindings. No credential copies are made.

The cache recovery guide now pauses new work, waits for active consumers, lists
references, and permits only individual removal of identified stopped stale
containers without --force. Cache removal/recreation/population/verification is
chained with && so a failure prevents later steps. No actual shared-cache cleanup
was performed.

Verification:
- Windows: 45 central tests, 43 passed and 2 skipped (POSIX signing and a filename
  containing double quotes); all 21 setup automation tests passed.
- Linux container: all 6 new credential-mount tests passed, including the quoted
  filename case. Tests execute the actual Jenkinsfile shell wrappers with Docker
  stubbed and cover both topologies, provider selection, no-credential steps,
  missing/relative/directory bindings and nonzero Docker exit propagation.
- Three isolated Docker runs used generated mount arguments and dummy keystore,
  Firebase and Google Play files. Each selected file was readable, writes failed,
  sibling credentials were inaccessible, and the original fixture stayed intact.
  Windows source spelling was adapted for Docker Desktop; target/readonly options
  came from the shell wrapper. No real credential or publishing API was used.
- The complete Jenkinsfile parsed with the Jenkins image's Groovy libraries.
  This is not execution of a live Jenkins Pipeline/Declarative engine.
- The three cache-recovery Bash blocks parsed; stubbed success/failure checks
  confirmed that the four-step reset sequence stops at each failing command.
- git diff --check and deliverable/requirements manifest verification passed.

These checks establish shell argument handling and Docker mount behavior, not a
signed Android build or service upload from a real Mac. Existing Jenkins services,
jobs, credentials, app repositories and shared caches were not changed. Publish
this central revision and verify an actual Mac signing/upload run to complete
host integration validation.

### Documentation and file organization: 2026-09-09

Consolidated the 18 maintained documents into a root README and three guides. The
separate agent instructions and immutable original requirements remain. Reviewed
source guides against setup/configuration/operations coverage, retaining all unique
workflows and historical evidence. Corrected conflicting Mac/Python/scheme guidance
and unsafe/unparseable recovery examples. A migration table records old locations.

Grouped native adapters/bundles under `scripts/android`, `scripts/ios` and
`scripts/upload`; moved setup/node tests into `tests/` and host/requirements manifests
into `manifests/`. Updated all runner/pipeline/bundle references. Public Python, Jenkins
and deployed Mac launcher entrypoints remain stable. The unconfirmed public answers
example now requires a reviewed fixed release placeholder instead of the historical
`v1.0.0` revision with its known validation failure. No live job is updated by this.

Verification:
- Unified Windows suite: 66 tests, 64 passed, 2 platform skips (POSIX native signing
  and a credential filename containing double quotes). Existing tests now assert
  relocated native/upload bundle paths and preparation directories.
- All 41 parameters occur exactly once in the configuration reference tables and
  match setup validation; public example rendering and CLI help remain valid.
- 113 relative document links/anchors, 71 Bash examples, 5 embedded Python examples,
  all repository Python files and the four host shell scripts passed structural
  checks. The new-host cache initializer refuses an existing volume.
- Prior staged Jenkins credential-mount fixes were preserved apart from bundle path
  substitutions; the targeted package-cache recovery steps were retained.
- Whitespace checks, deliverable/host manifests and original requirement hashes
  passed. Requirements files retain their original bytes and SHA-256 values.

The Docker Linux engine named pipe was unavailable during this pass. No container
checks, Groovy parsing, real Flutter builds, Mac/Xcode signing or provider uploads
were run for this reorganization. Earlier dated results remain historical evidence.
No Jenkins services/jobs/credentials, app repositories or shared caches were changed.

### Separate host setup guides: 2026-09-09

At the user's request, replaced the combined setup guide with Windows/WSL, Linux
and macOS guides. Each contains its applicable prerequisites and complete host setup
sequence; Windows/Linux each retain the guarded fresh-bootstrap alternative, and
Mac includes its own Docker image settings and cache provisioning. Configuration and
operations remain shared. All 47 original setup command blocks were preserved across
the split. Navigation, migration references and the preflight documentation pointer
were updated.

Verification: 182 relative links/anchors, 96 Bash examples, 5 embedded Python
blocks and all 41 parameter definitions passed checks. Repository/host manifests
were refreshed and original requirement hashes were preserved. This was a
documentation change; no platform builds or live Jenkins operations were performed.

### Jenkins parameter CSV: 2026-09-09

Added `documents/PARAMETERS.csv` with all 41 public Jenkins job parameters, categories,
types, expected values, defaults, examples, descriptions and conditional requirements.
Verified CSV round-trip parsing, unique parameter coverage, exact choices/defaults
against the setup/upload validators, credential-ID example syntax and documentation
links. Refreshed the deliverable manifest; original requirement hashes are unchanged.
No runtime configuration, Jenkins job or credential was changed.

### Spaced job names and Android staging release job: 2026-09-09

The user requested the exact job name `Android Staging Release`. Setup and guarded
bootstrap now accept internal spaces in flat job names while preserving the strict
project ownership ID format. Leading/trailing whitespace, path separators, control
characters and invalid lengths remain rejected. Job creation/update/build/status
URLs retain percent encoding; existing ownership and backup checks remain in place.

Verification: 69 Windows tests ran, 67 passed and two platform-specific tests were
skipped. New tests cover spaced-name URLs, backups, ownership and invalid names.
The complete Jenkinsfile parsed in a disposable Jenkins-image container. Bootstrap
parsing initially lacked workflow plugin classes; it passed after including the
image's installed plugin libraries. Parsing does not execute bootstrap or Jenkins
Declarative stages. Parameter CSV coverage and deliverable hashes remain checked.

Using local user-entered API authentication, created `Android Staging Release` on
the existing localhost controller and read back all 41 saved parameters. The app
repository/branch and public identity/API settings were inherited from `Flutter CI`;
environment is staging, mode release, platform android, signing Jenkins and uploads
none. The selected keystore ID is `android-release-keystore`. No build was queued
and no platform compilation, signing or upload success is claimed. Credentials stay
in Jenkins; API credentials were not written to setup files or logs.

### Android release artifact configuration audit: 2026-09-09

Inspected exact `Android Staging Release` build 1, its saved ParametersAction and
archived AAB, rather than relying on the current job defaults. Build result was
SUCCESS, duration 131977 ms. The app revision was
`300a69ddb70f1e76a797a556f6963840989147a9`; central tooling was
`309aada14c89b69dec05148c8632425439e575ac`. This validates that published tooling
revision, not the later uncommitted file reorganization.

Verified directly in the archived bundle: package `com.company.app`, application
label `Test app`, versionName `1.0.0`, versionCode `1`, AOT Dart libraries for three
ABIs, no debug kernel asset and no debuggable manifest attribute. Saved settings
were staging/release/android with no Android flavor; the matching workspace SUCCESS
marker was `staging release android`. Upload destination was none and its stage
was skipped. The merged manifest and archive identity agree.

The archived AAB is 44242149 bytes; SHA-256:
`66b98577c9bdeddb399260f1dc1d4052860e393a09c314df32f57ac5b0092ac8`.
Jarsigner reported a verified signature with self-signed-chain, no-timestamp and
JarInputStream ordering warnings. A separate Java JarFile verification fully read
all 80 payload entries: zero unsigned entries, one signer, no signature/digest error.
Signer certificate SHA-256:
`37c34b248f347063bf9de7db2fc7c62ba2d9ebffb3e07de72a692550c0817669`.
The signer was not named Android Debug. Saved parameters and the executed central
adapter selected Jenkins signing and overrode the app's original debug signing
configuration. The signer certificate was not independently compared with the
uploaded keystore certificate; no signing secrets were read/exported for this audit.

Application compatibility limitation: the exact app revision contains only
`lib/main.dart` under lib, which hardcodes `Flutter Demo` and
`Flutter Demo Home Page`, reads no CI Dart defines and contains no API client. The
executed runner passes ENVIRONMENT, APP_NAME and API_BASE_URL as Dart defines, but
the app does not consume them. The AOT binary contains both hardcoded titles and
does not contain the configured `https://example.com` URL. Thus the native launcher
name is correct, while API/environment/in-screen-title behavior is not configured
by these values in this app. No application source or job settings were changed.

This audit establishes the archived release artifact's native configuration and
signature integrity, not installation/device behavior, Play acceptance, a separate
staging backend, or Mac/iOS integration. Verification copies were kept outside the
repository; manifests were refreshed and original requirements remain unchanged.

### Firebase App Distribution through Fastlane: 2026-09-09

Replaced the Firebase CLI upload command with the central Fastlane Firebase App
Distribution action. The upload bundle pins `fastlane-plugin-firebase_app_distribution`
1.0.0 alongside the existing Fastlane 2.239.0, with locked API dependencies and
checksums. Android Firebase and iOS Firebase now prepare that bundle before Jenkins
binds the selected service-account file. Existing per-job app IDs, group aliases,
release notes, upload destinations and archive-before-upload behavior remain.

The runner passes the verified debug APK, release AAB or signed release IPA explicitly
to the plugin. It runs outside the app checkout with an isolated environment and
only the selected publishing credential. App repositories need no Fastfile, Pluginfile,
Firebase SDK or configuration files. Firebase CLI is no longer needed for uploads;
the existing Docker image may still include it.

Verification on 2026-09-09:
- Full Windows Python suite: 71 tests ran, 69 passed and two platform-specific
  cases skipped. Coverage includes setup rendering, upload validation, credential
  isolation, APK/AAB/IPA selection, optional values and sanitized provider failures.
- The full Jenkinsfile parsed and its real upload helper passed 12 isolated Groovy
  cases in a disposable Jenkins-image container. Firebase and store destinations
  prepare dependencies before binding credentials, failed installation prevents
  binding/upload, and disabled destinations skip both. Jenkins steps were stubbed.
- The frozen upload bundle installed in a disposable `flutter-ci:1.0` Linux container.
  Ruby syntax passed. Six tests loaded the real Firebase plugin and validated
  APK/AAB/IPA options, with and without groups/release notes. Publishing was stubbed.
- Parameter/example coverage, local documentation links, whitespace and all three
  manifests passed checks. Original requirements and host files retain their hashes.

No real Firebase upload or native Mac bundle installation was performed. These
checks do not establish Firebase authentication, service acceptance, tester
installation or Jenkins Declarative integration. No live Jenkins jobs, credentials,
app repositories or shared dependency caches were changed.

### Configurable Android APK/AAB output: 2026-09-09

Added the per-job `ANDROID_ARTIFACT_TYPE` choice (`apk` or `aab`) at the user's
request. Build, identity verification, archive and upload use the selected format.
The existing build mode and signing configuration apply to that single artifact.
Missing settings preserve APK for debug and AAB for release. Google Play validation
requires release mode plus AAB. No automatic second artifact or diagnostic-output
change is included.

The pasted Jenkins log for central revision `87d282c` shows a successful Android
release AAB build/archive and Fastlane installation, followed by a suppressed
Firebase upload failure. The user confirmed that Google Play linkage is not set up
and selected release APK distribution. An APK avoids the AAB linkage prerequisite;
the original log alone does not establish whether another service error occurred.

Verification:
- Full Windows Python suite: 77 tests ran, 75 passed and two platform-specific cases
  skipped. Covers selection, old-job defaults, setup rendering, invalid values,
  correct upload file selection and Google Play restrictions.
- Complete Jenkinsfile parsing and 17 isolated Groovy cases passed: 12 existing
  upload-helper cases and five single-artifact archive cases. Jenkins steps stubbed.
- A real `ANDROID_ARTIFACT_TYPE=apk`, release-mode build completed from disposable
  app revision `300a69ddb70f1e76a797a556f6963840989147a9` using a generated test
  keystore through the existing Jenkins signing adapter. The central runner verified
  package/name; Android apksigner verified the APK signature. Its certificate SHA-256
  matched the generated keystore:
  `7594bd950f20752cf94660c9194ea3db987bd22c973d433d2fe9f617aaf6c0be`.
  Output contained only app.apk (44.1 MB reported by Flutter) and SUCCESS.
  Gradle assembleRelease took 71.6 seconds. Shared caches were mounted read-only
  and copied inside the disposable container. No real publishing credential was used.

No live Jenkins settings, Firebase upload or app repository changes were made by
this validation. To use the parameter in an existing job, publish the central change
and save `ANDROID_ARTIFACT_TYPE=apk` on that job while retaining release mode and its
existing signing/upload settings.

Parameter reference completion: after the user closed the locked CSV, added
ANDROID_ARTIFACT_TYPE to documents/PARAMETERS.csv and verified all 42 parameters,
choice values, example and Markdown coverage. Refreshed FILES.csv and verified
repository, host and unchanged original-requirement hashes. No runtime changes
or repeated platform builds were needed for this documentation completion.
