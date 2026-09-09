# Linux (Ubuntu) host setup

This guide sets up a Docker Jenkins controller and the Linux image for Android and Web on Linux (Ubuntu). iOS uses a separate native Mac agent. Follow this guide once per host, then use [Configuration](CONFIGURATION.md) for jobs and [Operations](OPERATIONS.md) for troubleshooting, backups and validation evidence.

Other hosts: [Windows/WSL](SETUP_WINDOWS_WSL.md), [macOS](SETUP_MACOS.md).

- [Requirements and preparation](#prepare)
- [Install host prerequisites](#ubuntu)
- [Get the central repository](#checkout)
- [Prepare images and caches](#linux-image)
- [Start Jenkins with the manual wizard](#docker-controller)
- [Optional Mac agent for iOS](#mac-agent)
- [Create jobs and verify builds](#first-build)
- [Alternative: guarded fresh bootstrap](#fresh-bootstrap)

<a id="prepare"></a>
## Requirements and preparation

All CI files stay in this central repository. Jenkins checks out tooling and the app separately, adapts only its disposable app checkout and never commits or pushes app changes. Publish this repository to a Git host Jenkins can reach. Have the app repository URL/branch, display name, Android application ID and iOS bundle ID ready. Credentials belong in Jenkins or protected host bindings; configuration contains credential IDs only.

Android/Web use Linux containers on every path. iOS needs a Mac and full Xcode. The pipeline detects a container named `jenkins` on the selected Docker daemon: when present it uses `--volumes-from jenkins`; otherwise it bind-mounts the host workspace at the same absolute path. Changing a label alone does not provision a remote Docker worker or repair its workspace mounts.

The containerized recipes target x86-64, not ARM Windows/Linux or Windows containers. For a Mac controller, use the separate [Mac guide](SETUP_MACOS.md); Apple Silicon uses amd64 emulation. [Operations](OPERATIONS.md) preserves reported timings and the limits of recorded integration evidence.

Start with 4+ CPU cores, 12-16 GB RAM available to Docker and 100 GB free SSD for one Docker build at a time. These are sizing recommendations, not guaranteed minima. Caches, image layers and archived artifacts grow over time. Serialize heavy builds.

Provide outbound access to Docker Hub, Ubuntu/Debian/Docker package repositories, GitHub, Google Flutter/Android downloads, Pub, Maven/Gradle, RubyGems, npm/NodeSource, Jenkins update/download sites, your Git server and selected upload service APIs. Configure corporate proxies/custom CA certificates in the host and relevant images when required.

Jenkins and trusted build code control the Docker host through its socket. The supplied containerized controller runs as root to match build-output ownership. Use only trusted repositories/pipeline code, keep authentication enabled and retain the localhost HTTP binding. No inbound-agent TCP port is published. A remote Mac needs an authenticated route, such as an SSH tunnel or a deliberately configured TLS reverse proxy supporting WebSockets. Localhost-only Jenkins does not receive public webhooks; use Poll SCM until ingress is configured.

**Choose the controller path before starting.** For an existing instance preserve its home/jobs/credentials and use the [existing-controller helper](CONFIGURATION.md#automation). For a new Docker controller choose either the [manual wizard](#docker-controller) or [guarded bootstrap](#fresh-bootstrap), never both. Bootstrap requires a new empty home and must not be mounted into an existing controller.

<a id="ubuntu"></a>
## Ubuntu: install Docker Engine

Use Ubuntu Server 24.04 x86-64 and an administrator account. If Docker already works, inspect `docker version`/`docker compose version` and skip installation. Preserve its installation/data. For other releases or conflicting packages follow the [official Docker instructions](https://docs.docker.com/engine/install/ubuntu/); those combinations were not validated here.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable\n' \
  "$(dpkg --print-architecture)" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out/back in for group membership. The `docker` group grants host control; restrict membership to trusted administrators. Verify:

```bash
docker version
docker compose version
docker run --rm hello-world
```

Linux/WSL hosts do not need native Flutter, Android Studio, Java, Ruby or Fastlane; those run in images. Python 3.10+ is needed where you run optional setup helpers.

<a id="checkout"></a>
## Get the central repository

Use a stable directory for the complete central checkout, including hidden files:

```bash
mkdir -p ~/ci
git clone "<your-central-repo-url>" ~/ci/flutter-cicd-central
cd ~/ci/flutter-cicd-central
```

Replace the placeholder URL; use an existing checkout if already present. No host/CI files go into Flutter repositories. [The host manifest](../manifests/host.csv) lists host deliverables/checksums; preserve `.env.example`, `.dockerignore` and other hidden files when transferring the folder.

<a id="linux-image"></a>
## Prepare the shared Linux image and caches

### Check the host and choose versions

On this Linux host, run the read-only preflight from `host/`:

```bash
cd ~/ci/flutter-cicd-central/host
bash check-host.sh
```

It checks Docker/Compose, Linux mode, amd64, the local socket/selected daemon match, Compose parsing and absence of a `jenkins` container. If that container exists, preserve it and use the existing-controller path. `bash check-host.sh --allow-existing` is diagnostic, not migration. On the native Mac path use [the Mac preflight](SETUP_MACOS.md#mac-prerequisites); this Linux guard intentionally refuses Apple Silicon.

From `host/`, preserve an existing `.env` or create it once:

```bash
cp -n .env.example .env
nano .env
```

| Setting | Packaged default | Purpose |
| --- | --- | --- |
| `FLUTTER_VERSION` | `3.47.0` | Flutter Git release ref built into the image |
| `ANDROID_CMDLINE_TOOLS_VERSION` | `15859902` | Android command-line tools archive version |
| `JENKINS_BASE_IMAGE` | `jenkins/jenkins:2.568.3-jdk21` | New Docker controller base |
| `JENKINS_HTTP_PORT` | `8080` | Docker controller localhost port |

These are infrastructure settings, never credentials. Match the Mac agent's exact Flutter version. Editing `.env` does not update an existing image: rebuild and verify it. The containerized controller must remain named `jenkins`. The image is `flutter-ci:1.0`; set each job's `FLUTTER_IMAGE` if choosing another.

The Flutter recipe includes Ubuntu 24.04, the selected Flutter/Dart SDK (packaged Flutter 3.47.0; verify the bundled Dart version with the smoke check), Java 17, Android platform 36/build tools, Ruby, Bundler 4.0.20, Node.js 22 and Firebase CLI 15.29.0. The runner invokes Flutter directly. Native Ruby dependencies are central in `scripts/ios/Gemfile`; Fastlane uploads use `scripts/upload/Gemfile`. The image still includes Firebase CLI, but distribution uses the locked Fastlane Firebase plugin. Uploads require the per-job settings and credentials in [Configuration](CONFIGURATION.md#firebase).

The Jenkins image adds Docker CLI, Git and the versioned [plugin set](../host/jenkins/plugins.txt), preserving the setup wizard/authentication ([official image documentation](https://github.com/jenkinsci/docker/blob/master/README.md)). Upstream packages/downloads can change: recipes are not byte-for-byte image locks. For a fleet, build/validate once, publish reviewed images to your registry and pin approved digests. Image/plugin changes do not automatically migrate an existing controller.

### Build and smoke-check

For a new Linux/WSL Docker controller, from `host/`:

```bash
docker compose --profile tools config --quiet
docker compose --profile tools build flutter-ci jenkins
docker image inspect flutter-ci:1.0 --format '{{.Id}}'
docker image inspect flutter-cicd-jenkins:1.0 --format '{{.Id}}'
```

`flutter-ci` is build-only under the `tools` profile, not a running service. Wait for success; initial downloads span several gigabytes. Provision only where authorized to accept the Android SDK licenses accepted by the image build.

```bash
docker run --rm flutter-ci:1.0 bash -c 'set -e
  flutter --version; java -version; ruby --version
  bundle --version; sdkmanager --version; node --version; firebase --version'
```

For the Docker-controller path also check:

```bash
docker run --rm --entrypoint bash flutter-cicd-jenkins:1.0 -c 'set -e
  java -version; git --version; docker --version'
```

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

<a id="docker-controller"></a>
## Start a new containerized Jenkins controller

Use only after the Linux/WSL preflight passes and only for the manual wizard. If using [bootstrap](#fresh-bootstrap), skip this section. Do not start over an existing `jenkins` container or reuse an existing home as a new installation.

From `host/`:

```bash
docker compose up -d jenkins
docker compose ps
docker compose logs --tail=100 jenkins
```

Wait until Jenkins is fully running. Open `http://localhost:8080` on the host (Windows can use Desktop/WSL forwarding), substituting your chosen port. For remote Ubuntu, forward from your workstation:

```bash
ssh -L 8080:127.0.0.1:8080 your-user@your-ci-host
```

Open workstation `http://localhost:8080`. Retrieve the unlock password locally:

```bash
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Enter it in the wizard, select suggested plugins, create an administrator and set the reachable Jenkins URL. Keep the password out of source control/shared logs. Verify Pipeline, Git and Timestamper are enabled under **Manage Jenkins > Plugins > Installed**.

Under **Manage Jenkins > Nodes > Built-In Node > Configure**, set one executor, allow builds and retain `/var/jenkins_home/workspace`. Save. This matches `LINUX_AGENT_LABEL=built-in` and shares its workspace volume. One executor serializes jobs using it; also avoid heavy overlapping work on other agents sharing the physical host.

Verify inside the controller, not only on the Docker host:

```bash
docker exec jenkins docker version
docker exec jenkins docker image inspect flutter-ci:1.0 --format '{{.Id}}'
docker exec jenkins sh -c 'mkdir -p /var/jenkins_home/workspace/host-check && printf "shared-workspace-ok\n" > /var/jenkins_home/workspace/host-check/probe.txt'
docker exec jenkins docker run --rm --volumes-from jenkins \
  -w /var/jenkins_home/workspace/host-check flutter-ci:1.0 cat probe.txt
```

The last command must print `shared-workspace-ok`, proving daemon and workspace access. Do not `chmod 777` the socket. Converting to non-root requires aligning socket permissions, build user and workspace ownership together.

The default Compose project stores jobs, credentials, workspaces/history/artifacts in `flutter-cicd_jenkins_home`. Changing project name can select another volume and make Jenkins appear empty. Routine restart preserves it; `docker compose down --volumes` deletes it. [Operations](OPERATIONS.md) contains restart, backup, retention and upgrade procedures. Continue to [jobs](#first-build), or add a Mac for iOS.

<a id="mac-agent"></a>
## Optional: add a Mac agent for iOS

Windows and Linux cannot compile iOS. On a separate Mac, follow [native prerequisites](SETUP_MACOS.md#mac-prerequisites) and [connect the Mac agent](SETUP_MACOS.md#mac-agent) to this controller. Preserve this controller; skip the Mac controller and Mac Docker sections when adding only an iOS agent.

Use one executor, the `flutter-macos` label and an exclusive inbound WebSocket node. Match the native Flutter version to this host's image. The Mac must reach the controller through a trusted route (an authenticated SSH tunnel or TLS ingress supporting WebSockets); the default localhost-only binding is not remotely reachable by itself. Configure iOS signing in [Configuration](CONFIGURATION.md#ios-signing) before a release build.

<a id="first-build"></a>
## Create jobs and verify the first builds

[Configuration](CONFIGURATION.md) contains every parameter, Jenkins UI instructions, confirmed answers, validate/render/apply helpers, Git credentials, signing and uploads. Store real answers/XML outside both repositories. Pipeline SCM points to this repository's root `Jenkinsfile`; job parameters select the app and tracked branch. Each copied job retains its separately configurable settings.

Start with `PLATFORM=web`, `BUILD_MODE=debug`, then verify Android. Select iOS or all platforms only after adding the separate Mac agent. A connected agent/preflight does not establish successful builds. Release Android produces an AAB with existing app signing or Jenkins-managed keystore signing. Release iOS produces a signed IPA; Jenkins-managed signing uses an ephemeral keychain, checks profile team/app/name and cleans temporary material. Existing-keychain mode needs already usable credentials. No signing assets are bundled.

Uploads stay `none` until configured. Provider credentials are separate from signing credentials. Firebase iOS needs a suitable signed export/device provisioning; App Store Connect needs `app-store-connect` export and its own API-key JSON. App Store Connect uploading does not submit App Review or release publicly. Firebase uploading does not make an unregistered device eligible for installation. Google Play publication depends on the configured track/status. Uploads follow artifact archival; [Configuration](CONFIGURATION.md#uploads) gives exact conditions.

Run once to establish the app SCM polling baseline; repeat after changing app repository/branch. Track the exact queue/build number and verify archived artifacts, native names/IDs, intended signing and saved settings. Verify an authorized app update triggers the selected job; do not push an unrequested test app commit. [Operations](OPERATIONS.md) records dated evidence and remaining integration checks. Tool/image/startup/stub success does not prove Git authentication, Android/iOS compilation, signing, service uploads, webhooks or Mac compatibility.

<a id="fresh-bootstrap"></a>
## Optional fresh Docker controller bootstrap

Use this optional path only for a **new Linux/WSL Docker host with no container named `jenkins`**, a new empty Jenkins home volume, and confirmed public answers. Reuse an existing controller with `automation/scripts/setup.py ensure-job` instead. Do not mount this bootstrap into an existing controller or reset its Jenkins home.

[Configuration](CONFIGURATION.md) covers public answers, jobs and credentials; [Mac setup](SETUP_MACOS.md#mac-agent) covers native agents. This bootstrap creates a secured administrator and one configured central Pipeline job. It does not copy files into a Flutter application or start the first build.

### Prepare the public answers and job XML

Run from the central package root on the Linux/WSL Docker host. First publish the central package to the confirmed CI repository/ref, so Jenkins can retrieve its Jenkinsfile. Choose a new state directory outside both Git repositories. The paths and volume name below are examples to confirm or replace.

```bash
set -eu
export CENTRAL_STATE="$HOME/flutter-central-bootstrap"
export CENTRAL_JENKINS_VOLUME="flutter-cicd-central-home-new"
mkdir -m 700 "$CENTRAL_STATE"
cp automation/answers.example.json "$CENTRAL_STATE/answers.json"
```

Fill every documented field in `answers.json` with the user's confirmed values, including the CI repository/ref, application repository/branch, saved job parameters and polling schedule. Set `confirmed` to `true` after collecting those values. Store only credential **IDs**; never put tokens, signing passwords or certificates into this JSON.

Choose the host image/tool versions and HTTP port in the environment before building. The following are the packaged example versions, not application settings:

```bash
export FLUTTER_VERSION="3.47.0"
export ANDROID_CMDLINE_TOOLS_VERSION="15859902"
export JENKINS_BASE_IMAGE="jenkins/jenkins:2.568.3-jdk21"
export JENKINS_HTTP_PORT="8080"
python3 automation/scripts/setup.py validate --config "$CENTRAL_STATE/answers.json"
python3 automation/scripts/setup.py render-job --config "$CENTRAL_STATE/answers.json" --output "$CENTRAL_STATE/job.xml"
cp automation/assets/bootstrap.groovy "$CENTRAL_STATE/bootstrap.groovy"
```

The answers' `jenkins.url` must be the reachable URL for this controller. The job's `FLUTTER_IMAGE` must match the built image (`flutter-ci:1.0` with the packaged Compose file).

### Create one Compose override

Save the following as `$CENTRAL_STATE/bootstrap.compose.yaml`. Its environment variables must remain literal in the YAML. Bash's quoted heredoc below preserves them.

```bash
cat > "$CENTRAL_STATE/bootstrap.compose.yaml" <<'YAML'
services:
  jenkins:
    volumes:
      - type: bind
        source: ${CENTRAL_STATE}/answers.json
        target: /usr/share/jenkins/ref/central-answers.json
        read_only: true
        bind:
          create_host_path: false
      - type: bind
        source: ${CENTRAL_STATE}/job.xml
        target: /usr/share/jenkins/ref/central-job.xml
        read_only: true
        bind:
          create_host_path: false
      - type: bind
        source: ${CENTRAL_STATE}/bootstrap.groovy
        target: /usr/share/jenkins/ref/init.groovy.d/20-central-bootstrap.groovy
        read_only: true
        bind:
          create_host_path: false
volumes:
  jenkins_home:
    external: true
    name: ${CENTRAL_JENKINS_VOLUME}
YAML
```

The override keeps the packaged Docker socket, workspace volume and fixed container name used by the pipeline. It leaves the setup wizard enabled: successful bootstrap marks setup complete itself; if initialization fails before that point, Jenkins retains its normal setup protection. Resolve the combined configuration and inspect its public host paths/ports before starting:

```bash
docker compose --project-name flutter-cicd-central -f host/compose.yaml -f "$CENTRAL_STATE/bootstrap.compose.yaml" config --quiet
```

### Guard the new home and start

These checks refuse an existing container or volume. Do not remove those checks, delete an existing volume, or use `down -v` to make the recipe continue.

```bash
docker info >/dev/null
if docker container inspect jenkins >/dev/null 2>&1; then
  printf '%s\n' 'A Jenkins container already exists. Use the existing-controller setup.'
  exit 1
fi
if docker volume inspect "$CENTRAL_JENKINS_VOLUME" >/dev/null 2>&1; then
  printf '%s\n' 'The chosen volume already exists. Choose a new volume name.'
  exit 1
fi
docker compose --project-name flutter-cicd-central -f host/compose.yaml -f "$CENTRAL_STATE/bootstrap.compose.yaml" build flutter-ci jenkins
docker volume create --label flutter-cicd-central.bootstrap=true "$CENTRAL_JENKINS_VOLUME"
docker run --rm --user 0:0 --entrypoint sh -v "$CENTRAL_JENKINS_VOLUME:/var/jenkins_home" flutter-cicd-jenkins:1.0 -ec '
  test -z "$(find /var/jenkins_home -mindepth 1 -maxdepth 1 -print -quit)"
  umask 077
  printf "%s\n" flutter-cicd-central-v1 > /var/jenkins_home/.flutter-cicd-central-fresh-home
'
docker compose --project-name flutter-cicd-central -f host/compose.yaml -f "$CENTRAL_STATE/bootstrap.compose.yaml" up -d jenkins
```

The marker is written only after the new volume is checked empty. The bootstrap consumes `.flutter-cicd-central-fresh-home`, creates `.flutter-cicd-central-setup-complete`, and records a fingerprint in `.flutter-cicd-central-bootstrap.json`. An interrupted initialization can resume only with identical answers and XML. A completed initialization is skipped on restart. If initialization fails, inspect it; do not erase its state or alter its marker to bypass a check.

After Jenkins starts, verify completion without printing its secrets:

```bash
docker exec jenkins test -f /var/jenkins_home/.flutter-cicd-central-setup-complete
```

That command can fail while Jenkins is still starting. Retry after startup; inspect the Jenkins log if it remains unsuccessful. The bootstrap has not queued a build.

### Credentials, agents and first build

The new administrator is `flutter-cicd-admin`. Its random password is stored, mode `0600`, at:

`/var/jenkins_home/secrets/flutter-cicd-central-admin-password`

Keep that value in protected local storage/process bindings. Do not put it into answers, source control, command arguments, chat or build logs. The helper supports Jenkins API tokens through `JENKINS_API_TOKEN`; on this fresh host, its crumb-aware client can also use the bootstrap administrator password in that protected variable.

For an agent operating on this host, the following reads the password internally and uses it without displaying it. Shell tracing is disabled first:

```bash
set +x
export JENKINS_USER="flutter-cicd-admin"
export JENKINS_API_TOKEN
JENKINS_API_TOKEN="$(docker exec jenkins cat /var/jenkins_home/secrets/flutter-cicd-central-admin-password)"
python3 automation/scripts/setup.py status --config "$CENTRAL_STATE/answers.json"
```

Add the required repository/signing credentials in Jenkins using the IDs in the saved job settings, and provision the required Linux/Mac agents. For iOS, use the native Mac host guide and `automation/scripts/macos_agent.py`. Neither bootstrap nor a successful job creation proves that credentials, agents or builds are ready.

When those prerequisites are ready, explicitly start the first build:

```bash
python3 automation/scripts/setup.py build --config "$CENTRAL_STATE/answers.json"
```

Record its returned `queue_id`. Check that exact queue item until `executable.number` is assigned, then check the exact build number:

```bash
python3 automation/scripts/setup.py status --config "$CENTRAL_STATE/answers.json" --queue-id 1
python3 automation/scripts/setup.py status --config "$CENTRAL_STATE/answers.json" --build-number 1
unset JENKINS_API_TOKEN
```

Replace `1` with the returned queue/build identifiers. Verify the result and archived artifacts before reporting completion. The first application checkout establishes the tracked application branch for Poll SCM. Subsequent app updates use the job's saved settings. If the app repository or tracked branch is changed later, run a build to establish that new checkout before relying on polling.

Keep the state directory and the same Compose override available for future restarts; its bind-mounted files are required by the saved Compose configuration. Keep the Jenkins volume and credentials backed up through your normal Jenkins backup process.

